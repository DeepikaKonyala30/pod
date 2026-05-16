"""
PodMind — Storage Agent

Analyzes PVC I/O metrics to detect:
  1. PVC saturation (current IOPS near estimated device limit)
  2. Time-shift correlation between PVC saturation and pod restarts
  3. Large sequential write detection (> 50 MB/s for > 30s)

Input:  PVC write rates, pod-to-PVC mappings, pod restart events
Output: StorageAgentOutput (Pydantic validated)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from agents.schemas import (
    BulkWriteRecord,
    CausalHypothesis,
    PVCSaturationRecord,
    StorageAgentOutput,
)

logger = logging.getLogger("podmind.agents.storage")


class StorageAgent:
    """
    Specialized storage/PVC analysis agent.

    Detects I/O saturation, correlates PVC throughput with pod restarts,
    and identifies bulk write workloads that may impact co-located pods.
    """

    def __init__(
        self,
        saturation_threshold: float = 0.7,
        bulk_write_threshold_mb: float = 50.0,
        bulk_write_duration_sec: float = 30.0,
        restart_lookback_samples: int = 24,  # 2 min at 5s intervals
    ):
        self._sat_threshold = saturation_threshold
        self._bulk_write_mb = bulk_write_threshold_mb
        self._bulk_write_dur = bulk_write_duration_sec
        self._restart_lookback = restart_lookback_samples

    async def analyze(
        self,
        storage_data: dict[str, pd.DataFrame],
        pod_pvc_mapping: dict[str, list[str]] | None = None,
        events: list[dict[str, Any]] | None = None,
        volume_stats: list[dict[str, Any]] | None = None,
    ) -> StorageAgentOutput:
        """
        Run full storage analysis.

        Args:
            storage_data: {"ns:pod": DataFrame with 'write_bytes_per_sec'}.
            pod_pvc_mapping: {"ns:pod": ["pvc_name1", ...]}.
            events: Recent K8s events for restart correlation.
            volume_stats: Volume stats from kubelet for capacity info.
        """
        if not storage_data:
            logger.warning("No storage data available for analysis")
            return StorageAgentOutput()

        # Estimate device IOPS baseline from historical p99
        baseline_iops = self._estimate_baseline(storage_data)

        # Step 1: PVC saturation detection
        saturated_pvcs = self._detect_saturation(
            storage_data, baseline_iops, pod_pvc_mapping or {}
        )

        # Step 2: Restart causal hypothesis
        hypotheses = []
        if events:
            hypotheses = self._correlate_restarts(
                storage_data, events, baseline_iops
            )

        # Step 3: Bulk write detection
        bulk_writers = self._detect_bulk_writes(storage_data)

        window_start, window_end = self._get_window_bounds(storage_data)

        output = StorageAgentOutput(
            saturated_pvcs=saturated_pvcs,
            restart_causal_hypotheses=hypotheses,
            bulk_writers=bulk_writers,
            total_pvcs_analyzed=len(storage_data),
            window_start=window_start,
            window_end=window_end,
        )

        logger.info(
            "Storage Agent: %d saturated PVCs, %d causal hypotheses, %d bulk writers",
            len(saturated_pvcs), len(hypotheses), len(bulk_writers),
        )

        return output

    # -------------------------------------------------------------------------
    # Baseline Estimation
    # -------------------------------------------------------------------------

    def _estimate_baseline(
        self, storage_data: dict[str, pd.DataFrame]
    ) -> float:
        """
        Estimate device IOPS limit from historical p99 across all pods.
        Uses the maximum observed write rate as a proxy for device capacity.
        """
        all_max = []
        for df in storage_data.values():
            if "write_bytes_per_sec" in df.columns:
                vals = df["write_bytes_per_sec"].dropna()
                if len(vals) > 0:
                    all_max.append(float(vals.max()))

        if all_max:
            # Use p99 of all maximums as baseline estimate
            return float(np.percentile(all_max, 99)) * 1.2  # 20% headroom
        return 100_000_000.0  # Default 100 MB/s fallback

    # -------------------------------------------------------------------------
    # Step 1: PVC Saturation Detection
    # -------------------------------------------------------------------------

    def _detect_saturation(
        self,
        storage_data: dict[str, pd.DataFrame],
        baseline: float,
        pod_pvc_mapping: dict[str, list[str]],
    ) -> list[PVCSaturationRecord]:
        """Detect PVCs with I/O near estimated device capacity."""
        saturated = []

        for key, df in storage_data.items():
            if df.empty or "write_bytes_per_sec" not in df.columns:
                continue

            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            namespace, pod = parts

            mean_write = float(df["write_bytes_per_sec"].dropna().mean())
            saturation_score = mean_write / baseline if baseline > 0 else 0.0

            if saturation_score >= self._sat_threshold:
                pvc_names = pod_pvc_mapping.get(key, [])
                pvc_name = pvc_names[0] if pvc_names else f"ephemeral-{pod}"

                saturated.append(PVCSaturationRecord(
                    pvc_name=pvc_name,
                    namespace=namespace,
                    saturation_score=round(min(saturation_score, 1.0), 3),
                    write_bytes_per_sec=round(mean_write, 2),
                    pods_affected=[pod],
                ))

        return sorted(saturated, key=lambda x: x.saturation_score, reverse=True)

    # -------------------------------------------------------------------------
    # Step 2: PVC Saturation → Restart Correlation
    # -------------------------------------------------------------------------

    def _correlate_restarts(
        self,
        storage_data: dict[str, pd.DataFrame],
        events: list[dict[str, Any]],
        baseline: float,
    ) -> list[CausalHypothesis]:
        """
        For each pod restart event, check PVC saturation in the preceding
        2-minute window. If saturation > threshold, record causal hypothesis.
        """
        restart_events = [e for e in events if e.get("is_restart")]
        hypotheses = []

        for event in restart_events:
            pod = event.get("involved_object_name", "")
            ns = event.get("namespace", "")

            # Check all storage data for saturation near the restart time
            for key, df in storage_data.items():
                if df.empty or "write_bytes_per_sec" not in df.columns:
                    continue

                # Look at the last 2 minutes of data
                recent = df["write_bytes_per_sec"].dropna()
                if len(recent) < 5:
                    continue

                lookback = recent.iloc[-self._restart_lookback:]
                mean_write = float(lookback.mean())
                sat_score = mean_write / baseline if baseline > 0 else 0.0

                parts = key.split(":", 1)
                writer_pod = parts[1] if len(parts) == 2 else key

                if sat_score > self._sat_threshold and writer_pod != pod:
                    hypotheses.append(CausalHypothesis(
                        pod=pod,
                        namespace=ns,
                        pvc_name=f"shared-pvc-{ns}",
                        restart_time=event.get("timestamp", ""),
                        pvc_saturation_before_restart=round(min(sat_score, 1.0), 3),
                        hypothesis=(
                            f"PVC saturation ({sat_score:.0%}) by {writer_pod} "
                            f"likely caused {pod} restart via I/O starvation"
                        ),
                        confidence=round(min(sat_score, 1.0), 3),
                    ))

        return hypotheses

    # -------------------------------------------------------------------------
    # Step 3: Bulk Sequential Write Detection
    # -------------------------------------------------------------------------

    def _detect_bulk_writes(
        self, storage_data: dict[str, pd.DataFrame]
    ) -> list[BulkWriteRecord]:
        """
        Detect pods writing > 50 MB/s for > 30 consecutive seconds.
        """
        threshold_bytes = self._bulk_write_mb * 1024 * 1024
        min_samples = int(self._bulk_write_dur / 5)  # 6 samples at 5s

        bulk_writers = []

        for key, df in storage_data.items():
            if df.empty or "write_bytes_per_sec" not in df.columns:
                continue

            values = df["write_bytes_per_sec"].dropna().values

            # Find consecutive runs above threshold
            above = values > threshold_bytes
            if not np.any(above):
                continue

            # Count max consecutive True values
            max_run = 0
            current_run = 0
            for v in above:
                if v:
                    current_run += 1
                    max_run = max(max_run, current_run)
                else:
                    current_run = 0

            if max_run >= min_samples:
                parts = key.split(":", 1)
                if len(parts) == 2:
                    mean_rate = float(values[above].mean())
                    bulk_writers.append(BulkWriteRecord(
                        pod=parts[1],
                        namespace=parts[0],
                        write_rate_mb_per_sec=round(mean_rate / (1024 * 1024), 1),
                        duration_seconds=float(max_run * 5),
                    ))

        return bulk_writers

    def _get_window_bounds(self, data):
        starts, ends = [], []
        for df in data.values():
            if not df.empty and isinstance(df.index, pd.DatetimeIndex):
                starts.append(int(df.index.min().timestamp()))
                ends.append(int(df.index.max().timestamp()))
        return (min(starts) if starts else None, max(ends) if ends else None)
