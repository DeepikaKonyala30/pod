"""
PodMind — Agent Orchestrator (LangGraph DAG)

Manages the parallel execution of all four AI agents, the dependency mapper,
and the forecaster using a LangGraph StateGraph DAG. Replaces raw asyncio.gather
with a proper graph-based execution model for traceability and composability.

Execution DAG:
  [START]
     │
     ▼
  parallel_agents (cpu + mem + stor + net via asyncio.gather)
     │
     ▼
  dependency_mapper
     │
     ▼
  forecaster
     │
     ▼
  [END → AnalysisCycleOutput]

FIX G3: Uses asyncio.gather inside a single parallel_agents node to achieve
true parallel execution within the LangGraph framework.

FIX VULN-01: dependency_mapper and forecaster use async thread-pool offloading
for heavy CPU-bound computations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from agents.cpu_agent import CPUAgent
from agents.memory_agent import MemoryAgent
from agents.storage_agent import StorageAgent
from agents.network_agent import NetworkAgent
from agents.dependency_mapper import DependencyMapper
from agents.forecaster import Forecaster
from agents.schemas import (
    AnalysisCycleOutput,
    CPUAgentOutput,
    DependencyGraph,
    MemoryAgentOutput,
    NetworkAgentOutput,
    PodForecast,
    StorageAgentOutput,
)

logger = logging.getLogger("podmind.agents.orchestrator")


# =============================================================================
# LangGraph State Schema
# =============================================================================

class OrchestratorState(TypedDict, total=False):
    """State passed through the LangGraph DAG at each step."""
    # --- Input data (set at START) ---
    cpu_data: dict[str, pd.DataFrame]
    cpu_throttle: dict[str, pd.DataFrame]
    memory_data: dict[str, pd.DataFrame]
    storage_data: dict[str, pd.DataFrame]
    network_data: dict[str, pd.DataFrame]
    log_summaries: Optional[dict[str, dict[str, Any]]]
    events: Optional[list[dict[str, Any]]]
    pod_pvc_mapping: Optional[dict[str, list[str]]]
    pod_metadata: Optional[list[dict[str, Any]]]

    # --- Agent outputs (set by agent nodes) ---
    cpu_output: Optional[CPUAgentOutput]
    memory_output: Optional[MemoryAgentOutput]
    storage_output: Optional[StorageAgentOutput]
    network_output: Optional[NetworkAgentOutput]

    # --- Post-agent outputs ---
    dependency_graph: Optional[DependencyGraph]
    forecasts: list[PodForecast]
    cycle_start_time: float
    cycle_duration_ms: int


# =============================================================================
# LangGraph Node Functions
# =============================================================================

class AgentOrchestrator:
    """
    Orchestrates the multi-agent analysis pipeline using LangGraph StateGraph.

    Builds a DAG where the 4 agents execute in parallel (via asyncio.gather
    inside a single node), followed by sequential dependency mapping and forecasting.

    FIX G3: True parallel agent execution via asyncio.gather within LangGraph.
    FIX VULN-01: Heavy ML computations offloaded to thread pool.
    """

    def __init__(
        self,
        contamination: float = 0.1,
        granger_max_lag: int = 6,
        granger_p_threshold: float = 0.05,
        forecast_horizon_minutes: int = 60,
    ):
        # Initialize specialized agents
        self._cpu_agent = CPUAgent(contamination=contamination)
        self._memory_agent = MemoryAgent()
        self._storage_agent = StorageAgent()
        self._network_agent = NetworkAgent()
        self._dependency_mapper = DependencyMapper(
            max_lag=granger_max_lag,
            p_threshold=granger_p_threshold,
        )
        self._forecaster = Forecaster(
            horizon_minutes=forecast_horizon_minutes,
        )

        # Build the LangGraph DAG
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """
        Construct the LangGraph StateGraph DAG.

        Topology (FIX G3 — true parallel via fan-out):
            START → parallel_agents (runs all 4 agents via asyncio.gather)
                  → dependency_mapper (sequential, thread-pool offloaded)
                  → forecaster (sequential, thread-pool offloaded)
                  → END
        """
        builder = StateGraph(OrchestratorState)

        # Register nodes
        builder.add_node("parallel_agents", self._parallel_agents_node)
        builder.add_node("dependency_mapper", self._dependency_node)
        builder.add_node("forecaster", self._forecast_node)

        # Linear DAG: parallel_agents → dependency_mapper → forecaster → END
        builder.set_entry_point("parallel_agents")
        builder.add_edge("parallel_agents", "dependency_mapper")
        builder.add_edge("dependency_mapper", "forecaster")
        builder.add_edge("forecaster", END)

        return builder.compile()

    # -------------------------------------------------------------------------
    # LangGraph Node Implementations
    # -------------------------------------------------------------------------

    async def _parallel_agents_node(self, state: OrchestratorState) -> dict:
        """
        Run all four agents in TRUE parallel via asyncio.gather.

        FIX G3: Instead of sequential edges (cpu→mem→stor→net), we use
        asyncio.gather inside a single LangGraph node to achieve real
        parallel execution of all four independent agents.
        """
        logger.info("  [Parallel Agents] Running CPU + Memory + Storage + Network concurrently...")

        cpu_out, mem_out, stor_out, net_out = await asyncio.gather(
            self._cpu_agent.analyze(
                state.get("cpu_data", {}),
                state.get("cpu_throttle", {}),
            ),
            self._memory_agent.analyze(
                state.get("memory_data", {}),
                state.get("events"),
            ),
            self._storage_agent.analyze(
                state.get("storage_data", {}),
                state.get("pod_pvc_mapping"),
                state.get("events"),
            ),
            self._network_agent.analyze(
                state.get("network_data", {}),
                state.get("log_summaries"),
            ),
        )

        logger.info(
            "  [Parallel Agents] Complete — CPU(%d anomalies) MEM(%d leaks) "
            "STOR(%d saturated) NET(%d saturated)",
            len(cpu_out.anomalous_pods),
            len(mem_out.leak_suspects),
            len(stor_out.saturated_pvcs),
            len(net_out.saturated_pods),
        )

        return {
            "cpu_output": cpu_out,
            "memory_output": mem_out,
            "storage_output": stor_out,
            "network_output": net_out,
        }

    async def _dependency_node(self, state: OrchestratorState) -> dict:
        """
        Build dependency graph via Granger causality.

        VULN-01 FIX: Uses build_async() which offloads heavy computation
        to a thread pool via asyncio.run_in_executor().
        """
        logger.info("  [Dependency Mapper] Building causal graph...")
        graph = await self._dependency_mapper.build_async(
            cpu_data=state.get("cpu_data", {}),
            memory_data=state.get("memory_data", {}),
            network_data=state.get("network_data", {}),
            pod_metadata=state.get("pod_metadata"),
        )
        logger.info("  [Dependency Mapper] %d nodes, %d edges",
                     len(graph.nodes), len(graph.edges))
        return {"dependency_graph": graph}

    async def _forecast_node(self, state: OrchestratorState) -> dict:
        """
        Generate forecasts for anomalous pods.

        VULN-01 FIX: Forecaster.forecast_pod() internally uses
        asyncio.run_in_executor() for Prophet/ARIMA fitting.
        """
        logger.info("  [Forecaster] Generating predictions...")

        # Collect anomalous pod keys for targeted forecasting
        anomalous_keys = set()
        cpu_out = state.get("cpu_output")
        mem_out = state.get("memory_output")

        if cpu_out:
            for a in cpu_out.anomalous_pods:
                anomalous_keys.add(f"{a.namespace}:{a.pod}")
        if mem_out:
            for l in mem_out.leak_suspects:
                anomalous_keys.add(f"{l.namespace}:{l.pod}")
            for o in mem_out.oom_risk_pods:
                anomalous_keys.add(f"{o.namespace}:{o.pod}")

        forecasts = []
        if anomalous_keys:
            forecasts = await self._forecaster.forecast_all(
                cpu_data=state.get("cpu_data", {}),
                memory_data=state.get("memory_data", {}),
                anomalous_pods=anomalous_keys,
            )

        logger.info("  [Forecaster] %d forecasts generated", len(forecasts))
        return {"forecasts": forecasts}

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def run_analysis_cycle(
        self,
        cpu_data: dict[str, pd.DataFrame],
        cpu_throttle: dict[str, pd.DataFrame],
        memory_data: dict[str, pd.DataFrame],
        storage_data: dict[str, pd.DataFrame],
        network_data: dict[str, pd.DataFrame],
        log_summaries: dict[str, dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
        pod_pvc_mapping: dict[str, list[str]] | None = None,
        pod_metadata: list[dict[str, Any]] | None = None,
    ) -> AnalysisCycleOutput:
        """
        Execute a complete analysis cycle via LangGraph.

        This is the main entry point called every 30 seconds by the scheduler.
        The LangGraph DAG ensures proper execution ordering and state management.
        """
        start_time = time.monotonic()

        logger.info("=" * 60)
        logger.info("Starting LangGraph analysis cycle")

        # Prepare initial state
        initial_state: OrchestratorState = {
            "cpu_data": cpu_data,
            "cpu_throttle": cpu_throttle,
            "memory_data": memory_data,
            "storage_data": storage_data,
            "network_data": network_data,
            "log_summaries": log_summaries,
            "events": events,
            "pod_pvc_mapping": pod_pvc_mapping,
            "pod_metadata": pod_metadata,
            "cycle_start_time": start_time,
        }

        # Execute the LangGraph DAG
        try:
            final_state = await self._graph.ainvoke(initial_state)
        except Exception as e:
            logger.error("LangGraph execution failed, falling back to asyncio: %s", str(e))
            return await self._fallback_analysis(
                cpu_data, cpu_throttle, memory_data, storage_data,
                network_data, log_summaries, events, pod_pvc_mapping, pod_metadata,
            )

        total_duration = int((time.monotonic() - start_time) * 1000)

        cpu_out = final_state.get("cpu_output", CPUAgentOutput())
        mem_out = final_state.get("memory_output", MemoryAgentOutput())
        stor_out = final_state.get("storage_output", StorageAgentOutput())
        net_out = final_state.get("network_output", NetworkAgentOutput())
        graph = final_state.get("dependency_graph", DependencyGraph())
        forecasts = final_state.get("forecasts", [])

        logger.info(
            "LangGraph cycle complete: %dms total | "
            "CPU(%d anomalies) MEM(%d leaks, %d OOM) "
            "STOR(%d saturated) NET(%d saturated) "
            "GRAPH(%d edges) FORECAST(%d)",
            total_duration,
            len(cpu_out.anomalous_pods),
            len(mem_out.leak_suspects),
            len(mem_out.oom_risk_pods),
            len(stor_out.saturated_pvcs),
            len(net_out.saturated_pods),
            len(graph.edges),
            len(forecasts),
        )
        logger.info("=" * 60)

        return AnalysisCycleOutput(
            cpu=cpu_out,
            memory=mem_out,
            storage=stor_out,
            network=net_out,
            dependency_graph=graph,
            forecasts=forecasts,
            cycle_duration_ms=total_duration,
        )

    async def _fallback_analysis(
        self,
        cpu_data, cpu_throttle, memory_data, storage_data,
        network_data, log_summaries, events, pod_pvc_mapping, pod_metadata,
    ) -> AnalysisCycleOutput:
        """
        Fallback to raw asyncio.gather if LangGraph fails.
        Ensures the system remains operational even if the DAG framework errors.
        """
        start_time = time.monotonic()

        cpu_out, mem_out, stor_out, net_out = await asyncio.gather(
            self._cpu_agent.analyze(cpu_data, cpu_throttle),
            self._memory_agent.analyze(memory_data, events),
            self._storage_agent.analyze(storage_data, pod_pvc_mapping, events),
            self._network_agent.analyze(network_data, log_summaries),
        )

        # VULN-01 FIX: Use async version for thread-pool offloading
        graph = await self._dependency_mapper.build_async(
            cpu_data=cpu_data,
            memory_data=memory_data,
            network_data=network_data,
            pod_metadata=pod_metadata,
        )

        anomalous_keys = set()
        for a in cpu_out.anomalous_pods:
            anomalous_keys.add(f"{a.namespace}:{a.pod}")
        for l in mem_out.leak_suspects:
            anomalous_keys.add(f"{l.namespace}:{l.pod}")

        forecasts = []
        if anomalous_keys:
            forecasts = await self._forecaster.forecast_all(
                cpu_data=cpu_data,
                memory_data=memory_data,
                anomalous_pods=anomalous_keys,
            )

        total_duration = int((time.monotonic() - start_time) * 1000)

        return AnalysisCycleOutput(
            cpu=cpu_out,
            memory=mem_out,
            storage=stor_out,
            network=net_out,
            dependency_graph=graph,
            forecasts=forecasts,
            cycle_duration_ms=total_duration,
        )

    def get_agent_summary(self, output: AnalysisCycleOutput) -> dict[str, Any]:
        """
        Generate a compact summary of the analysis cycle for the LLM prompt.

        Returns a dictionary that can be serialized to JSON and injected
        into the LLM prompt template.
        """
        return {
            "cpu_anomalies": [
                {
                    "pod": a.pod,
                    "namespace": a.namespace,
                    "score": a.anomaly_score,
                    "reason": a.reason,
                    "severity": a.severity.value,
                }
                for a in output.cpu.anomalous_pods
            ],
            "cpu_throttled": [
                {"pod": t.pod, "namespace": t.namespace, "throttle_pct": t.throttle_pct}
                for t in output.cpu.throttled_pods
            ],
            "memory_leaks": [
                {
                    "pod": l.pod,
                    "namespace": l.namespace,
                    "slope": l.slope_pct_per_min,
                    "current": l.current_usage_ratio,
                }
                for l in output.memory.leak_suspects
            ],
            "oom_risk": [
                {
                    "pod": o.pod,
                    "namespace": o.namespace,
                    "usage": o.usage_ratio,
                    "eta_min": o.eta_oom_min,
                }
                for o in output.memory.oom_risk_pods
            ],
            "storage_saturation": [
                {
                    "pvc": s.pvc_name,
                    "namespace": s.namespace,
                    "score": s.saturation_score,
                }
                for s in output.storage.saturated_pvcs
            ],
            "storage_causal": [
                {"pod": h.pod, "pvc": h.pvc_name, "hypothesis": h.hypothesis}
                for h in output.storage.restart_causal_hypotheses
            ],
            "network_saturated": [
                {"pod": s.pod, "direction": s.direction, "pct": s.saturation_pct}
                for s in output.network.saturated_pods
            ],
            "chatty_pods": [
                {"pod": c.pod, "pps": c.packets_per_sec}
                for c in output.network.chatty_pods
            ],
            "error_spikes": [
                {"pod": e.pod, "errors_per_min": e.errors_per_minute}
                for e in output.network.error_rate_spikes
            ],
            "dependency_edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "resource": e.resource_type.value,
                    "lag_sec": e.lag_seconds,
                    "p_value": e.p_value,
                }
                for e in output.dependency_graph.edges
            ],
            "forecasts": [
                {
                    "pod": f.pod,
                    "resource": f.resource_type.value,
                    "event": f.predicted_event,
                    "eta_min": f.eta_minutes,
                }
                for f in output.forecasts
                if f.predicted_event
            ],
            "cycle_duration_ms": output.cycle_duration_ms,
        }
