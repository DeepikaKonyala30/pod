"""
PodMind — Metric Normalizer

Transforms raw metrics into normalized, comparable values and resamples
all time-series to a uniform 5-second interval with forward-fill for gaps.

Normalization rules (per SRS §5.2.2):
  - CPU usage → percentage of pod's requested CPU limit (not absolute millicores)
  - Memory → usage-to-limit ratio (RSS / limit)
  - PVC throughput → normalized per GB of PVC capacity
  - All series resampled to uniform 5-second interval using forward-fill
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("podmind.collector.normalizer")


class MetricNormalizer:
    """
    Normalizes raw Prometheus metrics into comparable, bounded values
    and ensures uniform 5-second temporal resolution across all series.
    """

    def __init__(self, resample_interval: str = "5s"):
        """
        Args:
            resample_interval: Target resampling interval for all time-series.
        """
        self._resample_interval = resample_interval

    # -------------------------------------------------------------------------
    # CPU Normalization
    # -------------------------------------------------------------------------

    def normalize_cpu(
        self,
        cpu_usage: dict[str, pd.DataFrame],
        cpu_limits: dict[str, float],
    ) -> dict[str, pd.DataFrame]:
        """
        Normalize CPU usage as percentage of the pod's CPU limit.

        Args:
            cpu_usage: {"ns:pod": DataFrame with 'value' column (cores)}.
            cpu_limits: {"ns:pod": limit_cores}.

        Returns:
            {"ns:pod": DataFrame with 'cpu_usage_pct' column (0.0–1.0)}.
        """
        normalized = {}

        for key, df in cpu_usage.items():
            limit = cpu_limits.get(key, 0.0)
            df_resampled = self._resample(df)

            if limit > 0:
                df_resampled["cpu_usage_pct"] = (
                    df_resampled["value"] / limit
                ).clip(0.0, 2.0)  # Allow >100% (bursting above limit)
            else:
                # Pod has no CPU limit — flag it, use raw value
                df_resampled["cpu_usage_pct"] = df_resampled["value"]
                df_resampled["no_limit"] = True
                logger.debug("Pod %s has no CPU limit; using raw cores", key)

            df_resampled = df_resampled.drop(columns=["value"], errors="ignore")
            normalized[key] = df_resampled

        return normalized

    def normalize_cpu_throttle(
        self,
        throttle_data: dict[str, pd.DataFrame],
    ) -> dict[str, pd.DataFrame]:
        """
        Normalize CPU throttle ratios (already 0.0–1.0 from Prometheus).
        Resample to uniform interval and fill gaps.
        """
        normalized = {}
        for key, df in throttle_data.items():
            df_resampled = self._resample(df)
            df_resampled = df_resampled.rename(columns={"value": "throttle_ratio"})
            df_resampled["throttle_ratio"] = df_resampled["throttle_ratio"].clip(0.0, 1.0)
            normalized[key] = df_resampled

        return normalized

    # -------------------------------------------------------------------------
    # Memory Normalization
    # -------------------------------------------------------------------------

    def normalize_memory(
        self,
        memory_rss: dict[str, pd.DataFrame],
        memory_limits: dict[str, float],
        memory_cache: Optional[dict[str, pd.DataFrame]] = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Normalize memory as usage-to-limit ratio (RSS / limit).

        Args:
            memory_rss: {"ns:pod": DataFrame with 'value' column (bytes)}.
            memory_limits: {"ns:pod": limit_bytes}.
            memory_cache: Optional cache memory data for cache pressure analysis.

        Returns:
            {"ns:pod": DataFrame with 'memory_usage_ratio', 'memory_rss_bytes',
             and optionally 'cache_ratio' columns}.
        """
        normalized = {}

        for key, df in memory_rss.items():
            limit = memory_limits.get(key, 0.0)
            df_resampled = self._resample(df)

            df_resampled["memory_rss_bytes"] = df_resampled["value"]

            if limit > 0:
                df_resampled["memory_usage_ratio"] = (
                    df_resampled["value"] / limit
                ).clip(0.0, 2.0)
            else:
                df_resampled["memory_usage_ratio"] = 0.0
                df_resampled["no_limit"] = True
                logger.debug("Pod %s has no memory limit", key)

            # Add cache pressure ratio if available
            if memory_cache and key in memory_cache:
                cache_df = self._resample(memory_cache[key])
                df_resampled["cache_bytes"] = cache_df["value"]
                rss = df_resampled["memory_rss_bytes"].replace(0, np.nan)
                df_resampled["cache_ratio"] = (
                    df_resampled["cache_bytes"] / rss
                ).fillna(0.0).clip(0.0, 1.0)

            df_resampled = df_resampled.drop(columns=["value"], errors="ignore")
            normalized[key] = df_resampled

        return normalized

    # -------------------------------------------------------------------------
    # Network Normalization
    # -------------------------------------------------------------------------

    def normalize_network(
        self,
        rx_bytes: dict[str, pd.DataFrame],
        tx_bytes: dict[str, pd.DataFrame],
        rx_packets: Optional[dict[str, pd.DataFrame]] = None,
        estimated_nic_capacity_bytes: float = 125_000_000,  # 1 Gbps
    ) -> dict[str, pd.DataFrame]:
        """
        Normalize network metrics as percentage of estimated NIC capacity.

        Args:
            rx_bytes: Receive bytes/sec per pod.
            tx_bytes: Transmit bytes/sec per pod.
            rx_packets: Receive packets/sec per pod (for chatty pod detection).
            estimated_nic_capacity_bytes: Estimated NIC bandwidth in bytes/sec.

        Returns:
            {"ns:pod": DataFrame with 'rx_rate', 'tx_rate', 'rx_saturation',
             'tx_saturation', and optionally 'rx_packets_rate'}.
        """
        all_keys = set(rx_bytes.keys()) | set(tx_bytes.keys())
        normalized = {}

        for key in all_keys:
            frames = {}

            if key in rx_bytes:
                rx_df = self._resample(rx_bytes[key], interval="10s")
                frames["rx_rate"] = rx_df["value"]
                frames["rx_saturation"] = (
                    rx_df["value"] / estimated_nic_capacity_bytes
                ).clip(0.0, 1.0)

            if key in tx_bytes:
                tx_df = self._resample(tx_bytes[key], interval="10s")
                frames["tx_rate"] = tx_df["value"]
                frames["tx_saturation"] = (
                    tx_df["value"] / estimated_nic_capacity_bytes
                ).clip(0.0, 1.0)

            if rx_packets and key in rx_packets:
                pkt_df = self._resample(rx_packets[key], interval="10s")
                frames["rx_packets_rate"] = pkt_df["value"]

            if frames:
                normalized[key] = pd.DataFrame(frames)

        return normalized

    # -------------------------------------------------------------------------
    # PVC / Storage Normalization
    # -------------------------------------------------------------------------

    def normalize_pvc(
        self,
        fs_write_rate: dict[str, pd.DataFrame],
        pvc_capacities_gb: Optional[dict[str, float]] = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Normalize PVC throughput per GB of PVC capacity.

        Args:
            fs_write_rate: Filesystem write rate (bytes/sec) per pod.
            pvc_capacities_gb: {"ns:pvc": capacity_gb} for per-GB normalization.
        """
        normalized = {}

        for key, df in fs_write_rate.items():
            df_resampled = self._resample(df, interval="10s")
            df_resampled = df_resampled.rename(columns={"value": "write_bytes_per_sec"})

            # Normalize per GB if capacity is known
            if pvc_capacities_gb and key in pvc_capacities_gb:
                cap_gb = pvc_capacities_gb[key]
                if cap_gb > 0:
                    df_resampled["write_per_gb"] = (
                        df_resampled["write_bytes_per_sec"] / cap_gb
                    )

            normalized[key] = df_resampled

        return normalized

    # -------------------------------------------------------------------------
    # Resampling Utility
    # -------------------------------------------------------------------------

    def _resample(
        self,
        df: pd.DataFrame,
        interval: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Resample a DataFrame to a uniform time interval with forward-fill.

        Handles:
          - Non-uniform Prometheus scrape intervals
          - Missing samples (gaps in collection)
          - Duplicate timestamps
        """
        if df.empty:
            return df

        interval = interval or self._resample_interval

        # Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            logger.warning("DataFrame index is not DatetimeIndex; skipping resample")
            return df

        # Drop duplicate timestamps (keep last)
        df = df[~df.index.duplicated(keep="last")]

        # Sort by timestamp
        df = df.sort_index()

        # Resample with forward-fill (max 3 missing samples = 15s gap)
        df_resampled = df.resample(interval).ffill(limit=3)

        return df_resampled

    # -------------------------------------------------------------------------
    # Batch Normalization
    # -------------------------------------------------------------------------

    def normalize_all(
        self,
        cpu_usage: dict[str, pd.DataFrame],
        cpu_limits: dict[str, float],
        cpu_throttle: dict[str, pd.DataFrame],
        memory_rss: dict[str, pd.DataFrame],
        memory_limits: dict[str, float],
        memory_cache: dict[str, pd.DataFrame],
        network_rx: dict[str, pd.DataFrame],
        network_tx: dict[str, pd.DataFrame],
        network_packets: dict[str, pd.DataFrame],
        fs_write_rate: dict[str, pd.DataFrame],
    ) -> dict[str, dict[str, pd.DataFrame]]:
        """
        Run all normalizations in a single call.

        Returns a nested dict:
        {
            "cpu": {"ns:pod": DataFrame},
            "cpu_throttle": {"ns:pod": DataFrame},
            "memory": {"ns:pod": DataFrame},
            "network": {"ns:pod": DataFrame},
            "storage": {"ns:pod": DataFrame},
        }
        """
        return {
            "cpu": self.normalize_cpu(cpu_usage, cpu_limits),
            "cpu_throttle": self.normalize_cpu_throttle(cpu_throttle),
            "memory": self.normalize_memory(memory_rss, memory_limits, memory_cache),
            "network": self.normalize_network(network_rx, network_tx, network_packets),
            "storage": self.normalize_pvc(fs_write_rate),
        }
