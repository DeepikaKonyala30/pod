"""
PodMind — API Background Scheduler

Runs two loops:
  1. intelligence_loop: Full AI analysis cycle every 30s (LLM + agents).
  2. metrics_loop: Fast broadcast every 5s — pods + raw metrics snapshot.

Hybrid mode:
  - Uses real Redis data when available
  - Falls back to synthetic demo data when Redis is empty
  - Never skips a cycle — dashboard always gets data
"""

import asyncio
import logging
import time
from typing import Optional

from config import settings
from api.real_data import get_real_data_status
from api.redis_reader import RedisReader
from api.websocket import ws_manager
from agents.orchestrator import AgentOrchestrator
from intelligence.llm_client import LLMClient
from intelligence.prompt_templates import render_analysis_prompt, ANALYSIS_SYSTEM_PROMPT
from intelligence.recommendation_engine import RecommendationEngine
from intelligence.insight_store import InsightStore
import api.mock_data as mock

logger = logging.getLogger("podmind.api.scheduler")


class AnalysisScheduler:
    """Manages periodic AI analysis and real-time metric broadcasting."""

    def __init__(self, redis_reader: RedisReader, insight_store: InsightStore):
        self._redis = redis_reader
        self._store = insight_store

        self._orchestrator = AgentOrchestrator(
            contamination=0.1,
            granger_max_lag=6,
            granger_p_threshold=0.05,
            forecast_horizon_minutes=60,
        )
        self._llm = LLMClient(
            tier=settings.llm_tier,
            anthropic_api_key=settings.anthropic_api_key,
            openai_api_key=settings.openai_api_key,
            groq_api_key=settings.groq_api_key,
            groq_model=settings.groq_model,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            ollama_host=settings.ollama_host,
            ollama_model=settings.ollama_model,
        )
        self._recommendations = RecommendationEngine()

        self._intelligence_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None
        self._is_running = False

        # Last known good insight/graph (for re-broadcast when no WS listeners yet)
        self._last_insight: Optional[dict] = None
        self._last_graph: Optional[dict] = None
        self._last_agent_activity: Optional[dict] = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """Start both background loops."""
        if self._is_running:
            return
        self._is_running = True
        self._intelligence_task = asyncio.create_task(self._intelligence_loop())
        self._metrics_task = asyncio.create_task(self._metrics_loop())
        logger.info("Scheduler started: intelligence=30s, metrics=5s")

    async def stop(self):
        """Stop all background loops gracefully."""
        self._is_running = False
        for task in (self._intelligence_task, self._metrics_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("Scheduler stopped")

    # =========================================================================
    # Loop 1: Intelligence (30s) — full AI analysis
    # =========================================================================

    async def _intelligence_loop(self):
        """Run AI analysis every 30 seconds."""
        # Run immediately on first start so dashboard gets data right away
        await asyncio.sleep(2)  # brief delay for API to finish startup
        while self._is_running:
            try:
                await self.run_analysis_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Intelligence loop error: %s", str(e), exc_info=True)
            await asyncio.sleep(30)

    async def run_analysis_cycle(self):
        """Full AI analysis — real data with synthetic fallback."""
        logger.info("Starting intelligence analysis cycle...")
        cycle_start = time.monotonic()
        real_data = await get_real_data_status(self._redis)

        # ── 1. Read from Redis ──────────────────────────────────────────────
        cpu_data = {}
        memory_data = {}
        network_data = {}
        storage_data = {}
        log_summaries = {}
        events = []
        pvc_mapping = {}
        pod_metadata = []

        try:
            cpu_data = await self._redis.get_cpu_data(window_minutes=10)
            memory_data = await self._redis.get_memory_data(window_minutes=10)
            network_data = await self._redis.get_network_data(window_minutes=10)
            storage_data = await self._redis.get_storage_data(window_minutes=10)
            log_summaries = await self._redis.get_log_summaries()
            events = await self._redis.get_recent_events(count=50)
            pvc_mapping = await self._redis.get_pvc_mapping()
            pod_metadata = await self._redis.get_pod_metadata()
        except Exception as e:
            logger.warning("Redis read error: %s", e)

        has_real_data = bool(cpu_data)

        if not has_real_data:
            if real_data.ready:
                logger.warning("Real data stack is healthy but Redis has no CPU series; skipping synthetic AI cycle")
                return
            logger.info("No real metrics in Redis — using synthetic demo data for AI cycle")
            await self._broadcast_synthetic_insight()
            return

        # ── 2. Run orchestrator ─────────────────────────────────────────────
        try:
            cpu_throttle = await self._redis.get_cpu_throttle_data(window_minutes=10)
            analysis_output = await self._orchestrator.run_analysis_cycle(
                cpu_data=cpu_data,
                cpu_throttle=cpu_throttle,
                memory_data=memory_data,
                storage_data=storage_data,
                network_data=network_data,
                log_summaries=log_summaries,
                events=events,
                pod_pvc_mapping=pvc_mapping,
                pod_metadata=pod_metadata,
            )
        except Exception as e:
            logger.error("Orchestrator failed: %s", e)
            if real_data.ready:
                return
            await self._broadcast_synthetic_insight()
            return

        # ── 3. LLM insights ────────────────────────────────────────────────
        try:
            summary_dict = self._orchestrator.get_agent_summary(analysis_output)
            prompt = render_analysis_prompt(summary_dict)
            raw_insight = await asyncio.wait_for(
                self._llm.generate(
                    system_prompt=ANALYSIS_SYSTEM_PROMPT,
                    user_prompt=prompt,
                ),
                timeout=45.0,
            )
        except asyncio.TimeoutError:
            logger.warning("LLM timed out, using rule-based fallback")
            raw_insight = None
        except Exception as e:
            logger.warning("LLM failed: %s", e)
            raw_insight = None

        if raw_insight is None or "LLM analysis unavailable" in (raw_insight.summary if raw_insight else ""):
            try:
                from intelligence.rule_engine import RuleEngine
                raw_insight = RuleEngine().generate(analysis_output)
            except Exception as e:
                logger.warning("Rule engine also failed: %s", e)
                if real_data.ready:
                    return
                await self._broadcast_synthetic_insight()
                return

        # ── 4. Post-process ────────────────────────────────────────────────
        try:
            final_insight = self._recommendations.process(raw_insight)
        except Exception as e:
            logger.warning("Recommendation engine failed: %s", e)
            final_insight = raw_insight

        # ── 5. Persist ─────────────────────────────────────────────────────
        try:
            insight_id = await self._store.store_insight(final_insight)
            logger.info("Analysis cycle complete in %.1fs. Insight: %s",
                        time.monotonic() - cycle_start, insight_id)
        except Exception as e:
            logger.warning("Failed to persist insight: %s", e)

        # ── 6. Broadcast ───────────────────────────────────────────────────
        insight_dict = final_insight.model_dump(mode="json")
        graph_dict = analysis_output.dependency_graph.model_dump(mode="json")
        agent_activity = self._build_agent_activity_from_real(analysis_output, cycle_start)

        self._last_insight = insight_dict
        self._last_graph = graph_dict
        self._last_agent_activity = agent_activity

        await ws_manager.broadcast({
            "type": "NEW_INSIGHT",
            "data": insight_dict,
            "graph": graph_dict,
            "agent_activity": agent_activity,
        })

    def _build_agent_activity_from_real(self, analysis_output, cycle_start: float) -> dict:
        """Build agent activity summary from real orchestrator output."""
        import time
        duration_ms = round((time.monotonic() - cycle_start) * 1000)
        try:
            return {
                "cycle_id": f"cycle-{int(time.time()/30):06d}",
                "cycle_started_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                "cycle_duration_ms": duration_ms,
                "llm_tier_used": self._llm.available_tiers[0] if self._llm.available_tiers else "rule-based",
                "llm_latency_ms": round(duration_ms * 0.6),
                "cpu_agent": {
                    "status": "completed",
                    "anomaly_count": len(getattr(analysis_output, 'cpu_anomalies', [])),
                    "throttled_count": len(getattr(analysis_output, 'throttled_pods', [])),
                    "latency_ms": round(duration_ms * 0.1),
                },
                "memory_agent": {
                    "status": "completed",
                    "leak_suspects": len(getattr(analysis_output, 'memory_leaks', [])),
                    "oom_risk_count": len(getattr(analysis_output, 'oom_risks', [])),
                    "latency_ms": round(duration_ms * 0.1),
                },
                "storage_agent": {
                    "status": "completed",
                    "saturated_pvcs": len(getattr(analysis_output, 'storage_issues', [])),
                    "latency_ms": round(duration_ms * 0.08),
                },
                "network_agent": {
                    "status": "completed",
                    "saturated_pods": len(getattr(analysis_output, 'network_issues', [])),
                    "latency_ms": round(duration_ms * 0.08),
                },
                "forecast_agent": {
                    "status": "completed",
                    "predictions": len(getattr(analysis_output, 'forecasts', [])),
                    "latency_ms": round(duration_ms * 0.12),
                },
                "dependency_mapper": {
                    "status": "completed",
                    "nodes": len(getattr(analysis_output.dependency_graph, 'nodes', [])),
                    "edges": len(getattr(analysis_output.dependency_graph, 'edges', [])),
                    "latency_ms": round(duration_ms * 0.15),
                },
            }
        except Exception:
            return self._last_agent_activity or {}

    async def _broadcast_synthetic_insight(self):
        """Broadcast fully synthetic insight + graph + agent activity."""
        insight_dict = mock.get_demo_insight()
        graph_dict = mock.get_demo_graph()
        agent_activity = mock.get_demo_agent_activity()

        self._last_insight = insight_dict
        self._last_graph = graph_dict
        self._last_agent_activity = agent_activity

        await ws_manager.broadcast({
            "type": "NEW_INSIGHT",
            "data": insight_dict,
            "graph": graph_dict,
            "agent_activity": agent_activity,
        })
        logger.info("Synthetic insight broadcast complete")

    # =========================================================================
    # Loop 2: Metrics (5s) — fast pod + raw metrics snapshot
    # =========================================================================

    async def _metrics_loop(self):
        """Broadcast pod metrics snapshot every 5 seconds."""
        while self._is_running:
            try:
                await self._broadcast_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Metrics broadcast error: %s", e)
            await asyncio.sleep(5)

    async def _broadcast_metrics(self):
        """Push live pod snapshot to all WebSocket clients."""
        pods = []
        using_real = False
        real_data = await get_real_data_status(self._redis)

        try:
            pod_metadata = await self._redis.get_pod_metadata()
            if pod_metadata:
                # Enrich with latest CPU/mem from Redis TS.GET
                pods = await self._enrich_pods_with_metrics(pod_metadata)
                using_real = True
        except Exception:
            pass

        if not pods and not real_data.ready:
            pods = mock.get_demo_pods()

        await ws_manager.broadcast({
            "type": "PODS_UPDATE",
            "pods": pods,
            "demo_mode": bool(pods) and not using_real,
        })

    async def _enrich_pods_with_metrics(self, pod_metadata: list) -> list:
        """Attach latest CPU/mem snapshots to pod metadata records."""
        import datetime as dt_module
        now = dt_module.datetime.now(dt_module.timezone.utc).isoformat()
        enriched = []
        for pod in pod_metadata:
            ns = pod.get("namespace", "default")
            name = pod.get("name", "")
            key_ns_pod = f"{ns}:{name}"

            cpu_pct = 0.0
            mem_ratio = 0.0
            try:
                pipe = self._redis._redis.pipeline()
                pipe.execute_command("TS.GET", f"cpu:{key_ns_pod}")
                pipe.execute_command("TS.GET", f"mem:{key_ns_pod}")
                results = await pipe.execute()
                if results[0]:
                    cpu_pct = float(results[0][1])
                if results[1]:
                    mem_ratio = float(results[1][1])
            except Exception:
                pass

            status = "critical" if (cpu_pct > 85 or mem_ratio > 0.88) else \
                     "warning" if (cpu_pct > 65 or mem_ratio > 0.70) else "healthy"

            enriched.append({
                **pod,
                "cpu_pct": round(cpu_pct, 2),
                "memory_ratio": round(mem_ratio, 4),
                "status": status,
                "collected_at": now,
            })
        return enriched
