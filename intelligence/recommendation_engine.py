"""
PodMind — Recommendation Engine

Post-LLM processing that ranks, deduplicates, and prioritizes
recommendations from the LLM output. Also provides a rule-based
fallback when all LLM tiers are unavailable (NFR-04).

Processing pipeline:
  1. Receive InsightOutput from LLM
  2. Deduplicate recommendations by (pod, action_type)
  3. Rank root causes by composite severity score
  4. Assign priority tiers: immediate / short-term / long-term
  5. Generate rule-based fallback if no LLM output
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

logger = logging.getLogger("podmind.intelligence.recommendation")

# Priority weights for composite scoring
_SEVERITY_WEIGHT = {
    Severity.CRITICAL: 1.0,
    Severity.HIGH: 0.75,
    Severity.MEDIUM: 0.5,
    Severity.LOW: 0.25,
    Severity.INFO: 0.1,
}


class RecommendationEngine:
    """
    Post-processes LLM insights and generates rule-based fallback
    recommendations when the LLM is unavailable.
    """

    def process(self, insight: InsightOutput) -> InsightOutput:
        """
        Post-process LLM output: deduplicate, re-rank, assign priorities.

        Args:
            insight: Raw InsightOutput from LLM.

        Returns:
            Cleaned and re-ranked InsightOutput.
        """
        # Deduplicate recommendations
        deduped_recs = self._deduplicate_recommendations(insight.recommendations)

        # Re-rank root causes by composite score
        ranked_causes = self._rank_root_causes(insight.root_causes)

        return InsightOutput(
            root_causes=ranked_causes,
            recommendations=deduped_recs,
            forecast_alerts=insight.forecast_alerts,
            dependency_narrative=insight.dependency_narrative,
            summary=insight.summary,
            generated_at=insight.generated_at,
        )

    def generate_fallback(
        self, analysis: AnalysisCycleOutput
    ) -> InsightOutput:
        """
        Generate rule-based recommendations when LLM is unavailable.

        Uses deterministic rules based on agent outputs to produce
        actionable recommendations without LLM reasoning.

        Args:
            analysis: Complete analysis cycle output from agents.

        Returns:
            Rule-based InsightOutput.
        """
        root_causes = []
        recommendations = []
        forecast_alerts = []
        rank = 1

        # ---- CPU Rules ----
        for anomaly in analysis.cpu.anomalous_pods:
            root_causes.append(RootCause(
                rank=rank,
                pod=anomaly.pod,
                namespace=anomaly.namespace,
                resource=ResourceType.CPU,
                description=anomaly.reason,
                severity=anomaly.severity,
                confidence=anomaly.anomaly_score,
            ))
            rank += 1

        for throttled in analysis.cpu.throttled_pods:
            recommendations.append(Recommendation(
                pod=throttled.pod,
                namespace=throttled.namespace,
                action=(
                    f"Increase CPU limit. Current throttle rate: {throttled.throttle_pct:.1f}%. "
                    f"Run: kubectl set resources deployment/<owner> "
                    f"-n {throttled.namespace} --limits=cpu=<new_limit>"
                ),
                priority="immediate" if throttled.throttle_pct > 30 else "short-term",
                rationale=f"CPU throttling at {throttled.throttle_pct:.1f}% degrades latency",
            ))

        # ---- Memory Rules ----
        for leak in analysis.memory.leak_suspects:
            root_causes.append(RootCause(
                rank=rank,
                pod=leak.pod,
                namespace=leak.namespace,
                resource=ResourceType.MEMORY,
                description=(
                    f"Memory leak detected: growing at {leak.slope_pct_per_min:.2f}%/min "
                    f"(R²={leak.r_squared:.3f}), currently at {leak.current_usage_ratio:.1%}"
                ),
                severity=Severity.HIGH,
                confidence=leak.r_squared,
            ))
            rank += 1

            recommendations.append(Recommendation(
                pod=leak.pod,
                namespace=leak.namespace,
                action=(
                    f"Investigate memory leak: heap profiling recommended. "
                    f"Immediate: kubectl rollout restart deployment/<owner> -n {leak.namespace}"
                ),
                priority="immediate",
                rationale=f"Linear growth at {leak.slope_pct_per_min:.2f}%/min will cause OOM",
            ))

        for oom in analysis.memory.oom_risk_pods:
            severity = Severity.CRITICAL if oom.usage_ratio > 0.95 else Severity.HIGH
            root_causes.append(RootCause(
                rank=rank,
                pod=oom.pod,
                namespace=oom.namespace,
                resource=ResourceType.MEMORY,
                description=(
                    f"OOM risk: memory at {oom.usage_ratio:.1%} of limit"
                    + (f", ETA {oom.eta_oom_min:.0f}min" if oom.eta_oom_min else "")
                ),
                severity=severity,
                confidence=min(oom.usage_ratio + 0.1, 1.0),
            ))
            rank += 1

            if oom.eta_oom_min and oom.eta_oom_min < 60:
                forecast_alerts.append(ForecastAlert(
                    pod=oom.pod,
                    namespace=oom.namespace,
                    resource=ResourceType.MEMORY,
                    eta_minutes=oom.eta_oom_min,
                    predicted_event="OOM kill",
                    confidence=0.8,
                ))

        # ---- Storage Rules ----
        for sat in analysis.storage.saturated_pvcs:
            root_causes.append(RootCause(
                rank=rank,
                pod=sat.pods_affected[0] if sat.pods_affected else "unknown",
                namespace=sat.namespace,
                resource=ResourceType.STORAGE,
                description=(
                    f"PVC '{sat.pvc_name}' I/O saturated at {sat.saturation_score:.0%}"
                ),
                severity=Severity.HIGH if sat.saturation_score > 0.9 else Severity.MEDIUM,
                confidence=sat.saturation_score,
            ))
            rank += 1

        for hyp in analysis.storage.restart_causal_hypotheses:
            recommendations.append(Recommendation(
                pod=hyp.pod,
                namespace=hyp.namespace,
                action=(
                    f"Separate I/O workloads: move {hyp.pod} to dedicated PVC. "
                    f"{hyp.hypothesis}"
                ),
                priority="short-term",
                rationale=f"PVC saturation ({hyp.pvc_saturation_before_restart:.0%}) causing cascading restarts",
            ))

        # ---- Network Rules ----
        for sat in analysis.network.saturated_pods:
            root_causes.append(RootCause(
                rank=rank,
                pod=sat.pod,
                namespace=sat.namespace,
                resource=ResourceType.NETWORK,
                description=(
                    f"Network {sat.direction} saturated at {sat.saturation_pct:.1f}% "
                    f"({sat.bytes_per_sec:.0f} bytes/sec)"
                ),
                severity=Severity.HIGH,
                confidence=min(sat.saturation_pct / 100.0, 1.0),
            ))
            rank += 1

        for chatty in analysis.network.chatty_pods:
            recommendations.append(Recommendation(
                pod=chatty.pod,
                namespace=chatty.namespace,
                action=(
                    f"Investigate high packet rate ({chatty.packets_per_sec:.0f} pps). "
                    f"Consider NetworkPolicy to rate-limit or batch requests."
                ),
                priority="short-term",
                rationale=f"Packet rate {chatty.packets_per_sec:.0f} pps exceeds 10k threshold",
            ))

        # Re-rank and build output
        root_causes = self._rank_root_causes(root_causes)
        summary = self._build_summary(root_causes, recommendations, forecast_alerts)

        return InsightOutput(
            root_causes=root_causes,
            recommendations=recommendations,
            forecast_alerts=forecast_alerts,
            dependency_narrative=self._build_dep_narrative(analysis),
            summary=summary,
        )

    # -------------------------------------------------------------------------
    # Internal Processing
    # -------------------------------------------------------------------------

    def _deduplicate_recommendations(
        self, recs: list[Recommendation]
    ) -> list[Recommendation]:
        """Deduplicate by (pod, action substring)."""
        seen = set()
        unique = []
        for rec in recs:
            # Use first 50 chars of action as dedup key
            key = f"{rec.namespace}:{rec.pod}:{rec.action[:50]}"
            if key not in seen:
                seen.add(key)
                unique.append(rec)
        return unique

    def _rank_root_causes(self, causes: list[RootCause]) -> list[RootCause]:
        """Re-rank root causes by composite score (severity × confidence)."""
        def score(c: RootCause) -> float:
            return _SEVERITY_WEIGHT.get(c.severity, 0.5) * c.confidence

        sorted_causes = sorted(causes, key=score, reverse=True)
        # Update rank numbers
        for i, cause in enumerate(sorted_causes, start=1):
            cause.rank = i
        return sorted_causes

    def _build_summary(
        self,
        causes: list[RootCause],
        recs: list[Recommendation],
        alerts: list[ForecastAlert],
    ) -> str:
        """Generate executive summary from rule-based findings."""
        parts = []
        critical = [c for c in causes if c.severity == Severity.CRITICAL]
        high = [c for c in causes if c.severity == Severity.HIGH]

        if critical:
            parts.append(f"{len(critical)} critical issue(s) detected")
        if high:
            parts.append(f"{len(high)} high-severity finding(s)")
        if alerts:
            parts.append(f"{len(alerts)} predictive alert(s)")

        immediate = [r for r in recs if r.priority == "immediate"]
        if immediate:
            parts.append(f"{len(immediate)} immediate action(s) recommended")

        if not parts:
            return "Cluster health nominal. No anomalies detected."

        return ". ".join(parts) + "."

    def _build_dep_narrative(self, analysis: AnalysisCycleOutput) -> str:
        """Build dependency narrative from graph edges."""
        edges = analysis.dependency_graph.edges
        if not edges:
            return "No significant causal dependencies detected."

        lines = []
        for e in edges[:5]:  # Limit to top 5 edges
            lines.append(
                f"{e.source} → {e.target} ({e.resource_type.value}, "
                f"lag={e.lag_seconds}s, p={e.p_value:.4f})"
            )
        return (
            f"Detected {len(edges)} causal dependencies:\n" + "\n".join(lines)
        )
