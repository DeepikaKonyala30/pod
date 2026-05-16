"""
PodMind — Memory Agent

Analyzes per-pod memory metrics over a 10-minute rolling window to detect:
  1. Memory leaks (linear regression slope > 0.5%/min)
  2. OOM risk (utilization ratio > 85%)
  3. Cache pressure (cache memory > 60% of RSS)
  4. Memory spike → restart event correlations

Input:  10-minute window of memory usage ratios per pod (5s = 120 samples)
Output: MemoryAgentOutput (Pydantic validated)

VULN-04 FIX: Added min_uptime_minutes to skip leak detection for young
containers, preventing false positives during JVM/runtime warmup phases.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd

from agents.schemas import (
    CachePressureRecord,
    LeakRecord,
    MemoryAgentOutput,
    OOMRiskRecord,
    RestartCorrelation,
    Severity,
)

logger = logging.getLogger("podmind.agents.memory")


class MemoryAgent:
    """
    Specialized memory resource analysis agent.

    Uses linear regression for leak detection and correlates memory
    anomalies with pod restart events from the Kubernetes Events API.
    """

    def __init__(
        self,
        leak_slope_threshold: float = 0.005,
        oom_risk_threshold: float = 0.85,
        cache_pressure_threshold: float = 0.60,
        min_r_squared: float = 0.6,
        min_uptime_minutes: float = 5.0,
    ):
        """
        Args:
            leak_slope_threshold: Slope threshold for leak detection (ratio/min).
            oom_risk_threshold: Memory usage ratio threshold for OOM risk.
            cache_pressure_threshold: Cache/RSS ratio threshold.
            min_r_squared: Minimum R² for leak regression to be significant.
            min_uptime_minutes: VULN-04 FIX — Minimum container uptime (minutes)
                before leak detection is applied. Prevents false positives during
                JVM warmup, .NET JIT compilation, and Python import phases.
        """
        self._leak_slope = leak_slope_threshold
        self._oom_threshold = oom_risk_threshold
        self._cache_threshold = cache_pressure_threshold
        self._min_r2 = min_r_squared
        self._min_uptime_min = min_uptime_minutes

    async def analyze(
        self,
        memory_data: dict[str, pd.DataFrame],
        events: list[dict[str, Any]] | None = None,
        pod_metadata: list[dict[str, Any]] | None = None,
    ) -> MemoryAgentOutput:
        """
        Run full memory analysis.

        Args:
            memory_data: {"ns:pod": DataFrame with 'memory_usage_ratio' and
                          optionally 'cache_ratio' columns}.
            events: List of recent K8s events (from K8sClient.list_recent_events).
            pod_metadata: VULN-04 — Optional pod info dicts with 'start_time' to check uptime.
        """
        if not memory_data:
            logger.warning("No memory data available for analysis")
            return MemoryAgentOutput()

        # VULN-04 FIX: Build uptime map to skip young containers
        uptime_map = self._build_uptime_map(pod_metadata)

        leak_suspects = []
        oom_risk_pods = []
        cache_pressure_pods = []
        restart_correlations = []

        for key, df in memory_data.items():
            if df.empty or "memory_usage_ratio" not in df.columns:
                continue

            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            namespace, pod = parts

            values = df["memory_usage_ratio"].dropna()
            if len(values) < 20:
                continue

            # Step 1: Leak detection via linear regression
            # VULN-04 FIX: Skip leak detection for young containers
            uptime_min = uptime_map.get(key)
            if uptime_min is not None and uptime_min < self._min_uptime_min:
                logger.debug(
                    "Skipping leak detection for %s (uptime %.1fmin < %.1fmin threshold)",
                    key, uptime_min, self._min_uptime_min,
                )
                leak = None
            else:
                leak = self._detect_leak(values, pod, namespace)
            if leak:
                leak_suspects.append(leak)

            # Step 2: OOM risk assessment
            oom = self._assess_oom_risk(values, pod, namespace, leak)
            if oom:
                oom_risk_pods.append(oom)

            # Step 3: Cache pressure
            if "cache_ratio" in df.columns:
                cache = self._check_cache_pressure(
                    df["cache_ratio"].dropna(), pod, namespace
                )
                if cache:
                    cache_pressure_pods.append(cache)

        # Step 4: Restart correlations
        if events:
            restart_correlations = self._correlate_restarts(
                memory_data, events
            )

        window_start, window_end = self._get_window_bounds(memory_data)

        output = MemoryAgentOutput(
            leak_suspects=sorted(
                leak_suspects, key=lambda x: x.slope_pct_per_min, reverse=True
            ),
            oom_risk_pods=sorted(
                oom_risk_pods, key=lambda x: x.usage_ratio, reverse=True
            ),
            cache_pressure_pods=cache_pressure_pods,
            restart_correlations=restart_correlations,
            total_pods_analyzed=len(memory_data),
            window_start=window_start,
            window_end=window_end,
        )

        logger.info(
            "Memory Agent: %d leaks, %d OOM risk, %d cache pressure, %d restart corrs",
            len(leak_suspects), len(oom_risk_pods),
            len(cache_pressure_pods), len(restart_correlations),
        )

        return output

    # -------------------------------------------------------------------------
    # Step 1: Memory Leak Detection (Linear Regression)
    # -------------------------------------------------------------------------

    def _detect_leak(
        self,
        values: pd.Series,
        pod: str,
        namespace: str,
    ) -> LeakRecord | None:
        """
        Fit linear regression over the memory window.
        Flag as leak if slope > threshold and R² > min_r_squared.
        """
        y = values.values.astype(float)
        x = np.arange(len(y), dtype=float)

        # numpy.polyfit degree 1 = linear regression
        try:
            coeffs = np.polyfit(x, y, deg=1)
        except (np.linalg.LinAlgError, ValueError):
            return None

        slope = coeffs[0]      # Change per sample
        intercept = coeffs[1]

        # Convert slope from per-sample to per-minute
        # (samples are 5s apart, so 12 samples = 1 minute)
        slope_per_min = slope * 12.0

        # Compute R² to assess fit quality
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        if slope_per_min > self._leak_slope and r_squared > self._min_r2:
            return LeakRecord(
                pod=pod,
                namespace=namespace,
                slope_pct_per_min=round(slope_per_min * 100, 3),
                current_usage_ratio=round(float(y[-1]), 4),
                r_squared=round(r_squared, 3),
            )

        return None

    # -------------------------------------------------------------------------
    # Step 2: OOM Risk Assessment
    # -------------------------------------------------------------------------

    def _assess_oom_risk(
        self,
        values: pd.Series,
        pod: str,
        namespace: str,
        leak: LeakRecord | None,
    ) -> OOMRiskRecord | None:
        """Flag pods with memory utilization > OOM threshold in last sample."""
        current = float(values.iloc[-1])

        if current >= self._oom_threshold:
            # Estimate ETA to OOM if there's a leak
            eta_min = None
            if leak and leak.slope_pct_per_min > 0:
                remaining = (1.0 - current) * 100  # remaining %
                eta_min = remaining / leak.slope_pct_per_min

            return OOMRiskRecord(
                pod=pod,
                namespace=namespace,
                usage_ratio=round(current, 4),
                eta_oom_min=round(eta_min, 1) if eta_min else None,
            )

        return None

    # -------------------------------------------------------------------------
    # Step 3: Cache Pressure Analysis
    # -------------------------------------------------------------------------

    def _check_cache_pressure(
        self,
        cache_ratio: pd.Series,
        pod: str,
        namespace: str,
    ) -> CachePressureRecord | None:
        """Flag pods where cache memory exceeds threshold of RSS."""
        mean_cache_ratio = float(cache_ratio.mean())

        if mean_cache_ratio > self._cache_threshold:
            return CachePressureRecord(
                pod=pod,
                namespace=namespace,
                cache_ratio=round(mean_cache_ratio, 3),
            )

        return None

    # -------------------------------------------------------------------------
    # Step 4: Memory–Restart Correlation
    # -------------------------------------------------------------------------

    def _correlate_restarts(
        self,
        memory_data: dict[str, pd.DataFrame],
        events: list[dict[str, Any]],
    ) -> list[RestartCorrelation]:
        """
        For each pod restart event, check if there was a memory spike
        in the preceding 2-minute window.
        """
        restart_events = [
            e for e in events
            if e.get("is_restart") or e.get("is_oom")
        ]

        correlations = []

        for event in restart_events:
            pod = event.get("involved_object_name", "")
            ns = event.get("namespace", "")
            key = f"{ns}:{pod}"

            if key not in memory_data:
                continue

            df = memory_data[key]
            if df.empty or "memory_usage_ratio" not in df.columns:
                continue

            event_ts = event.get("timestamp_unix")
            if not event_ts:
                continue

            # Look at memory in the 2-minute window before the restart
            values = df["memory_usage_ratio"].dropna()
            if len(values) < 5:
                continue

            # Compute spike: max - mean in the window
            recent = values.iloc[-24:]  # Last 2 minutes (24 × 5s)
            if len(recent) < 5:
                continue

            mean_usage = float(recent.mean())
            max_usage = float(recent.max())
            spike = max_usage - mean_usage

            if spike > 0.05 or max_usage > 0.80:  # 5% spike or >80% usage
                correlations.append(RestartCorrelation(
                    pod=pod,
                    namespace=ns,
                    restart_time=event.get("timestamp", ""),
                    memory_spike_pct=round(spike * 100, 1),
                    correlation_strength=round(min(spike * 5, 1.0), 3),
                ))

        return correlations

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def _get_window_bounds(
        self, data: dict[str, pd.DataFrame]
    ) -> tuple[int | None, int | None]:
        """Get window start/end timestamps."""
        starts, ends = [], []
        for df in data.values():
            if not df.empty and isinstance(df.index, pd.DatetimeIndex):
                starts.append(int(df.index.min().timestamp()))
                ends.append(int(df.index.max().timestamp()))
        return (
            min(starts) if starts else None,
            max(ends) if ends else None,
        )

    def _build_uptime_map(
        self, pod_metadata: list[dict[str, Any]] | None
    ) -> dict[str, float | None]:
        """
        VULN-04 FIX: Build a mapping of "ns:pod" → uptime in minutes.

        Returns empty dict if no metadata available (all pods analyzed normally).
        """
        if not pod_metadata:
            return {}

        uptime_map: dict[str, float | None] = {}
        now = time.time()

        for meta in pod_metadata:
            name = meta.get("name", "")
            ns = meta.get("namespace", "")
            key = f"{ns}:{name}"

            start_time = meta.get("start_time") or meta.get("startTime")
            if start_time:
                try:
                    # Handle ISO 8601 string
                    if isinstance(start_time, str):
                        from datetime import datetime, timezone
                        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        start_epoch = dt.timestamp()
                    else:
                        start_epoch = float(start_time)

                    uptime_min = (now - start_epoch) / 60.0
                    uptime_map[key] = uptime_min
                except (ValueError, TypeError, OSError):
                    pass

        return uptime_map
