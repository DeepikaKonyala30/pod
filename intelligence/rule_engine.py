"""
PodMind — Rule-Based Fallback Engine

Deterministic recommendation engine that produces structured insights
when all LLM tiers are unavailable (NFR-04 compliance).

Uses threshold-based rules derived from the agent outputs to generate
reasonable recommendations without any ML/NLP processing.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.schemas import (
    AnalysisCycleOutput,
    ForecastAlert,
    InsightOutput,
    Recommendation,
    ResourceType,
    RootCause,
    Severity,
)

logger = logging.getLogger("podmind.intelligence.rule_engine")


class RuleEngine:
    """
    Deterministic, rule-based recommendation generator.

    Activated when all LLM tiers fail. Produces structured InsightOutput
    using threshold-based rules without any external API dependency.
    """

    # Threshold configuration
    CPU_THROTTLE_CRITICAL = 40.0   # %
    CPU_THROTTLE_HIGH = 20.0       # %
    MEMORY_OOM_CRITICAL = 0.95     # ratio
    MEMORY_OOM_HIGH = 0.85         # ratio
    MEMORY_LEAK_CRITICAL = 3.0     # %/min
    MEMORY_LEAK_HIGH = 1.0         # %/min
    STORAGE_SAT_CRITICAL = 0.95    # ratio
    STORAGE_SAT_HIGH = 0.80        # ratio
    NET_SAT_CRITICAL = 95.0        # %
    NET_SAT_HIGH = 80.0            # %

    def generate(self, analysis: AnalysisCycleOutput) -> InsightOutput:
        """
        Generate rule-based insights from agent outputs.

        Args:
            analysis: Complete analysis cycle output.

        Returns:
            InsightOutput with rule-based root causes and recommendations.
        """
        root_causes = []
        recommendations = []
        forecast_alerts = []
        rank = 1

        # ---- CPU Rules ----
        for t in analysis.cpu.throttled_pods:
            severity = (
                Severity.CRITICAL if t.throttle_pct > self.CPU_THROTTLE_CRITICAL
                else Severity.HIGH if t.throttle_pct > self.CPU_THROTTLE_HIGH
                else Severity.MEDIUM
            )
            root_causes.append(RootCause(
                rank=rank, pod=t.pod, namespace=t.namespace,
                resource=ResourceType.CPU,
                description=f"CPU throttled at {t.throttle_pct:.1f}%",
                severity=severity, confidence=0.95,
            ))
            recommendations.append(Recommendation(
                pod=t.pod, namespace=t.namespace,
                action=f"kubectl patch deployment -n {t.namespace} <deploy> -p "
                       f"'{{\"spec\":{{\"template\":{{\"spec\":{{\"containers\":[{{\"name\":\"main\","
                       f"\"resources\":{{\"limits\":{{\"cpu\":\"1000m\"}}}}}}]}}}}}}}}}'",
                priority="immediate" if severity == Severity.CRITICAL else "short-term",
                rationale=f"Throttle at {t.throttle_pct:.1f}% causes response latency spikes",
            ))
            rank += 1

        for a in analysis.cpu.anomalous_pods:
            root_causes.append(RootCause(
                rank=rank, pod=a.pod, namespace=a.namespace,
                resource=ResourceType.CPU,
                description=a.reason,
                severity=a.severity, confidence=a.anomaly_score,
            ))
            rank += 1

        # ---- Memory Rules ----
        for leak in analysis.memory.leak_suspects:
            severity = (
                Severity.CRITICAL if leak.slope_pct_per_min > self.MEMORY_LEAK_CRITICAL
                else Severity.HIGH
            )
            root_causes.append(RootCause(
                rank=rank, pod=leak.pod, namespace=leak.namespace,
                resource=ResourceType.MEMORY,
                description=f"Memory leak: {leak.slope_pct_per_min:.2f}%/min growth",
                severity=severity, confidence=leak.r_squared,
            ))
            recommendations.append(Recommendation(
                pod=leak.pod, namespace=leak.namespace,
                action=f"kubectl rollout restart deployment -n {leak.namespace} <deploy>; "
                       f"run heap profiler in next release",
                priority="immediate",
                rationale=f"Growth at {leak.slope_pct_per_min:.2f}%/min → OOM imminent",
            ))
            rank += 1

        for oom in analysis.memory.oom_risk_pods:
            severity = (
                Severity.CRITICAL if oom.usage_ratio > self.MEMORY_OOM_CRITICAL
                else Severity.HIGH
            )
            root_causes.append(RootCause(
                rank=rank, pod=oom.pod, namespace=oom.namespace,
                resource=ResourceType.MEMORY,
                description=f"Memory at {oom.usage_ratio:.1%}, OOM imminent",
                severity=severity, confidence=0.9,
            ))
            if oom.eta_oom_min:
                forecast_alerts.append(ForecastAlert(
                    pod=oom.pod, namespace=oom.namespace,
                    resource=ResourceType.MEMORY,
                    eta_minutes=oom.eta_oom_min,
                    predicted_event="OOM kill",
                    confidence=0.85,
                ))
            rank += 1

        # ---- Storage Rules ----
        for sat in analysis.storage.saturated_pvcs:
            severity = (
                Severity.CRITICAL if sat.saturation_score > self.STORAGE_SAT_CRITICAL
                else Severity.HIGH if sat.saturation_score > self.STORAGE_SAT_HIGH
                else Severity.MEDIUM
            )
            root_causes.append(RootCause(
                rank=rank,
                pod=sat.pods_affected[0] if sat.pods_affected else "unknown",
                namespace=sat.namespace,
                resource=ResourceType.STORAGE,
                description=f"PVC '{sat.pvc_name}' saturated at {sat.saturation_score:.0%}",
                severity=severity, confidence=sat.saturation_score,
            ))
            rank += 1

        # ---- Network Rules ----
        for sat in analysis.network.saturated_pods:
            severity = (
                Severity.CRITICAL if sat.saturation_pct > self.NET_SAT_CRITICAL
                else Severity.HIGH
            )
            root_causes.append(RootCause(
                rank=rank, pod=sat.pod, namespace=sat.namespace,
                resource=ResourceType.NETWORK,
                description=f"Network {sat.direction} at {sat.saturation_pct:.1f}%",
                severity=severity, confidence=0.9,
            ))
            rank += 1

        # Sort by severity weight × confidence
        weight = {Severity.CRITICAL: 1.0, Severity.HIGH: 0.75,
                  Severity.MEDIUM: 0.5, Severity.LOW: 0.25, Severity.INFO: 0.1}
        root_causes.sort(
            key=lambda c: weight.get(c.severity, 0.5) * c.confidence,
            reverse=True,
        )
        for i, c in enumerate(root_causes, 1):
            c.rank = i

        # Summary
        critical = sum(1 for c in root_causes if c.severity == Severity.CRITICAL)
        high = sum(1 for c in root_causes if c.severity == Severity.HIGH)
        summary_parts = []
        if critical:
            summary_parts.append(f"{critical} critical")
        if high:
            summary_parts.append(f"{high} high-severity")
        summary = (
            f"Rule-based analysis: {', '.join(summary_parts)} issue(s) detected. "
            f"{len(recommendations)} action(s) recommended."
            if summary_parts
            else "Cluster health nominal. No rule-based alerts triggered."
        )

        # Dependency narrative
        edges = analysis.dependency_graph.edges
        dep_narrative = "No significant dependencies detected."
        if edges:
            lines = [f"  {e.source} → {e.target} ({e.resource_type.value}, "
                     f"lag={e.lag_seconds}s)" for e in edges[:5]]
            dep_narrative = f"{len(edges)} causal dependencies found:\n" + "\n".join(lines)

        return InsightOutput(
            root_causes=root_causes,
            recommendations=recommendations,
            forecast_alerts=forecast_alerts,
            dependency_narrative=dep_narrative,
            summary=summary,
        )
