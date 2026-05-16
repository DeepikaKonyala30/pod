"""
PodMind — CPU Agent

Analyzes per-pod CPU metrics over a 10-minute rolling window to detect:
  1. Anomalous CPU patterns (Isolation Forest on coefficient of variation)
  2. Absolute CPU pressure (Z-score on p99 values)
  3. CPU throttling (throttle_ratio > 15%)
  4. Trending pods accelerating toward limits (numpy.gradient)

Input:  10-minute rolling window of CPU usage per pod (5s resolution = 120 samples)
Output: CPUAgentOutput (Pydantic validated)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from scipy import stats

from agents.schemas import (
    AnomalyRecord,
    CPUAgentOutput,
    ConsumerRecord,
    Severity,
    ThrottleRecord,
    TrendRecord,
)

logger = logging.getLogger("podmind.agents.cpu")


class CPUAgent:
    """
    Specialized CPU resource analysis agent.

    Processes normalized CPU time-series data and produces structured
    anomaly, throttle, trend, and top-consumer reports.
    """

    def __init__(
        self,
        contamination: float = 0.1,
        throttle_threshold: float = 0.15,
        z_score_threshold: float = 2.5,
        gradient_warning_threshold: float = 0.01,
    ):
        """
        Args:
            contamination: Isolation Forest contamination factor.
            throttle_threshold: CPU throttle ratio threshold (0.15 = 15%).
            z_score_threshold: Z-score threshold for absolute CPU pressure.
            gradient_warning_threshold: Min gradient to flag as trending.
        """
        self._contamination = contamination
        self._throttle_threshold = throttle_threshold
        self._z_score_threshold = z_score_threshold
        self._gradient_threshold = gradient_warning_threshold

    async def analyze(
        self,
        cpu_data: dict[str, pd.DataFrame],
        throttle_data: dict[str, pd.DataFrame] | None = None,
    ) -> CPUAgentOutput:
        """
        Run full CPU analysis on normalized metric windows.

        Args:
            cpu_data: {"ns:pod": DataFrame with 'cpu_usage_pct' column}.
            throttle_data: {"ns:pod": DataFrame with 'throttle_ratio' column}.

        Returns:
            Validated CPUAgentOutput with all findings.
        """
        if not cpu_data:
            logger.warning("No CPU data available for analysis")
            return CPUAgentOutput()

        # Compute per-pod statistics
        pod_stats = self._compute_pod_stats(cpu_data)

        if not pod_stats:
            return CPUAgentOutput()

        # Step 1: Isolation Forest on CV values
        anomalous = self._detect_anomalies(pod_stats)

        # Step 2: Z-score on p99 values
        z_anomalies = self._detect_z_score_anomalies(pod_stats)
        anomalous = self._merge_anomalies(anomalous, z_anomalies)

        # Step 3: Throttle detection
        throttled = self._detect_throttling(throttle_data or {})

        # Step 4: Gradient trending
        trending = self._detect_trends(cpu_data, pod_stats)

        # Step 5: Top consumers
        top_consumers = self._get_top_consumers(pod_stats, limit=10)

        # Determine window bounds
        window_start, window_end = self._get_window_bounds(cpu_data)

        output = CPUAgentOutput(
            anomalous_pods=anomalous,
            throttled_pods=throttled,
            trending_pods=trending,
            top_consumers=top_consumers,
            total_pods_analyzed=len(pod_stats),
            window_start=window_start,
            window_end=window_end,
        )

        logger.info(
            "CPU Agent: %d anomalies, %d throttled, %d trending (from %d pods)",
            len(anomalous), len(throttled), len(trending), len(pod_stats),
        )

        return output

    # -------------------------------------------------------------------------
    # Step 1: Isolation Forest Anomaly Detection
    # -------------------------------------------------------------------------

    def _compute_pod_stats(
        self, cpu_data: dict[str, pd.DataFrame]
    ) -> dict[str, dict[str, float]]:
        """Compute per-pod CPU statistics: mean, p95, p99, CV."""
        stats_map = {}

        for key, df in cpu_data.items():
            if df.empty or "cpu_usage_pct" not in df.columns:
                continue

            values = df["cpu_usage_pct"].dropna().values
            if len(values) < 10:  # Need minimum samples
                continue

            parts = key.split(":", 1)
            if len(parts) != 2:
                continue

            mean = float(np.mean(values))
            std = float(np.std(values))
            cv = std / mean if mean > 0 else 0.0

            stats_map[key] = {
                "namespace": parts[0],
                "pod": parts[1],
                "mean": mean,
                "std": std,
                "p95": float(np.percentile(values, 95)),
                "p99": float(np.percentile(values, 99)),
                "cv": cv,
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "samples": len(values),
            }

        return stats_map

    def _detect_anomalies(
        self, pod_stats: dict[str, dict[str, float]]
    ) -> list[AnomalyRecord]:
        """Apply Isolation Forest on CV values to detect bursty workloads."""
        if len(pod_stats) < 3:
            return []  # Need minimum pods for meaningful anomaly detection

        keys = list(pod_stats.keys())
        cv_values = np.array([[pod_stats[k]["cv"]] for k in keys])

        model = IsolationForest(
            contamination=min(self._contamination, 0.5),
            random_state=42,
            n_estimators=100,
        )
        predictions = model.fit_predict(cv_values)
        scores = model.decision_function(cv_values)

        anomalies = []
        for i, key in enumerate(keys):
            if predictions[i] == -1:  # Anomaly
                s = pod_stats[key]
                # Normalize score to 0-1 (lower decision function = more anomalous)
                norm_score = float(1.0 - (scores[i] - scores.min()) / (scores.max() - scores.min() + 1e-10))

                anomalies.append(AnomalyRecord(
                    pod=s["pod"],
                    namespace=s["namespace"],
                    anomaly_score=round(min(norm_score, 1.0), 3),
                    reason=f"Bursty CPU pattern: CV={s['cv']:.3f}, p99={s['p99']:.1%}",
                    severity=Severity.HIGH if norm_score > 0.7 else Severity.MEDIUM,
                ))

        return anomalies

    # -------------------------------------------------------------------------
    # Step 2: Z-Score Anomaly Detection
    # -------------------------------------------------------------------------

    def _detect_z_score_anomalies(
        self, pod_stats: dict[str, dict[str, float]]
    ) -> list[AnomalyRecord]:
        """Apply Z-score on p99 values to detect absolute CPU pressure."""
        if len(pod_stats) < 3:
            return []

        p99_values = np.array([s["p99"] for s in pod_stats.values()])
        mean_p99 = np.mean(p99_values)
        std_p99 = np.std(p99_values)

        if std_p99 < 1e-10:
            return []

        anomalies = []
        for key, s in pod_stats.items():
            z = (s["p99"] - mean_p99) / std_p99
            if z > self._z_score_threshold:
                anomalies.append(AnomalyRecord(
                    pod=s["pod"],
                    namespace=s["namespace"],
                    anomaly_score=round(min(float(z / 5.0), 1.0), 3),
                    reason=f"High CPU pressure: p99={s['p99']:.1%}, Z-score={z:.2f}",
                    severity=Severity.CRITICAL if z > 3.5 else Severity.HIGH,
                ))

        return anomalies

    def _merge_anomalies(
        self, a: list[AnomalyRecord], b: list[AnomalyRecord]
    ) -> list[AnomalyRecord]:
        """Merge two anomaly lists, keeping the highest score per pod."""
        merged = {}
        for record in a + b:
            k = f"{record.namespace}:{record.pod}"
            if k not in merged or record.anomaly_score > merged[k].anomaly_score:
                merged[k] = record
        return sorted(merged.values(), key=lambda x: x.anomaly_score, reverse=True)

    # -------------------------------------------------------------------------
    # Step 3: Throttle Detection
    # -------------------------------------------------------------------------

    def _detect_throttling(
        self, throttle_data: dict[str, pd.DataFrame]
    ) -> list[ThrottleRecord]:
        """Identify pods with CPU throttle ratio above threshold."""
        throttled = []

        for key, df in throttle_data.items():
            if df.empty or "throttle_ratio" not in df.columns:
                continue

            mean_throttle = float(df["throttle_ratio"].dropna().mean())
            if mean_throttle > self._throttle_threshold:
                parts = key.split(":", 1)
                if len(parts) == 2:
                    throttled.append(ThrottleRecord(
                        pod=parts[1],
                        namespace=parts[0],
                        throttle_pct=round(mean_throttle * 100, 1),
                    ))

        return sorted(throttled, key=lambda x: x.throttle_pct, reverse=True)

    # -------------------------------------------------------------------------
    # Step 4: Gradient Trending
    # -------------------------------------------------------------------------

    def _detect_trends(
        self,
        cpu_data: dict[str, pd.DataFrame],
        pod_stats: dict[str, dict[str, float]],
    ) -> list[TrendRecord]:
        """Detect pods accelerating toward CPU limits using numpy.gradient."""
        trending = []

        for key, df in cpu_data.items():
            if df.empty or "cpu_usage_pct" not in df.columns:
                continue
            if key not in pod_stats:
                continue

            values = df["cpu_usage_pct"].dropna().values
            if len(values) < 20:
                continue

            # Compute gradient (rate of change per sample)
            grad = np.gradient(values)
            mean_grad = float(np.mean(grad[-20:]))  # Focus on recent trend

            if mean_grad > self._gradient_threshold:
                s = pod_stats[key]
                # Estimate time to limit (1.0) from current level
                current = float(values[-1])
                remaining = max(1.0 - current, 0.0)
                # Gradient is per-sample (5s), convert to per-minute
                grad_per_min = mean_grad * 12.0
                eta_min = remaining / grad_per_min if grad_per_min > 0 else None

                trending.append(TrendRecord(
                    pod=s["pod"],
                    namespace=s["namespace"],
                    gradient=round(mean_grad, 6),
                    eta_to_limit_min=round(eta_min, 1) if eta_min else None,
                ))

        return sorted(trending, key=lambda x: x.gradient, reverse=True)

    # -------------------------------------------------------------------------
    # Step 5: Top Consumers
    # -------------------------------------------------------------------------

    def _get_top_consumers(
        self, pod_stats: dict[str, dict[str, float]], limit: int = 10
    ) -> list[ConsumerRecord]:
        """Get the top N CPU consumers by p99."""
        sorted_pods = sorted(
            pod_stats.values(), key=lambda x: x["p99"], reverse=True
        )
        return [
            ConsumerRecord(
                pod=s["pod"],
                namespace=s["namespace"],
                p99_cpu_pct=round(s["p99"] * 100, 1),
            )
            for s in sorted_pods[:limit]
        ]

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def _get_window_bounds(
        self, data: dict[str, pd.DataFrame]
    ) -> tuple[int | None, int | None]:
        """Get the earliest and latest timestamps across all DataFrames."""
        all_starts = []
        all_ends = []
        for df in data.values():
            if not df.empty and isinstance(df.index, pd.DatetimeIndex):
                all_starts.append(int(df.index.min().timestamp()))
                all_ends.append(int(df.index.max().timestamp()))

        return (
            min(all_starts) if all_starts else None,
            max(all_ends) if all_ends else None,
        )
