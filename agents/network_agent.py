"""
PodMind — Network / Log Agent

Analyzes per-pod network metrics and container logs to detect:
  1. Network saturation (rx/tx > 80% of NIC capacity)
  2. Chatty pods (packet rate > 10,000 pkt/sec)
  3. Log error rate spikes (ERROR/WARN/FATAL lines per minute)
  4. Connection pool exhaustion patterns in logs

Input:  Network rx/tx DataFrames, log summaries from LogCollector
Output: NetworkAgentOutput (Pydantic validated)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from agents.schemas import (
    ChattyPodRecord,
    ConnectionExhaustionRecord,
    ErrorRateRecord,
    NetworkAgentOutput,
    NetworkSaturationRecord,
)

logger = logging.getLogger("podmind.agents.network")


class NetworkAgent:
    """
    Specialized network and log analysis agent.

    Combines quantitative network metrics with qualitative log analysis
    to detect saturation, chatty behavior, and application-level errors.
    """

    def __init__(
        self,
        saturation_threshold: float = 0.80,
        chatty_threshold_pps: float = 10_000.0,
        error_rate_spike_threshold: float = 5.0,
    ):
        """
        Args:
            saturation_threshold: Network saturation ratio (0.8 = 80% of NIC).
            chatty_threshold_pps: Packets per second threshold for chatty pods.
            error_rate_spike_threshold: Errors per minute to flag as spike.
        """
        self._sat_threshold = saturation_threshold
        self._chatty_threshold = chatty_threshold_pps
        self._error_threshold = error_rate_spike_threshold

    async def analyze(
        self,
        network_data: dict[str, pd.DataFrame],
        log_summaries: dict[str, dict[str, Any]] | None = None,
    ) -> NetworkAgentOutput:
        """
        Run full network + log analysis.

        Args:
            network_data: {"ns:pod": DataFrame with 'rx_rate', 'tx_rate',
                          'rx_saturation', 'tx_saturation', 'rx_packets_rate'}.
            log_summaries: {"ns:pod": log summary dict from LogCollector}.
        """
        saturated_pods = []
        chatty_pods = []
        error_rate_spikes = []
        connection_exhaustion = []

        # ---- Network metric analysis ----
        if network_data:
            for key, df in network_data.items():
                if df.empty:
                    continue

                parts = key.split(":", 1)
                if len(parts) != 2:
                    continue
                namespace, pod = parts

                # Step 1: Network saturation
                sat_records = self._detect_saturation(df, pod, namespace)
                saturated_pods.extend(sat_records)

                # Step 2: Chatty pod detection
                chatty = self._detect_chatty(df, pod, namespace)
                if chatty:
                    chatty_pods.append(chatty)

        # ---- Log-based analysis ----
        if log_summaries:
            for key, summary in log_summaries.items():
                parts = key.split(":", 1)
                if len(parts) != 2:
                    continue
                namespace, pod = parts

                # Step 3: Error rate spikes
                error_record = self._detect_error_spike(summary, pod, namespace)
                if error_record:
                    error_rate_spikes.append(error_record)

                # Step 4: Connection pool exhaustion
                conn_record = self._detect_connection_exhaustion(
                    summary, pod, namespace
                )
                if conn_record:
                    connection_exhaustion.append(conn_record)

        total = len(network_data or {})
        output = NetworkAgentOutput(
            saturated_pods=sorted(
                saturated_pods, key=lambda x: x.saturation_pct, reverse=True
            ),
            chatty_pods=sorted(
                chatty_pods, key=lambda x: x.packets_per_sec, reverse=True
            ),
            error_rate_spikes=sorted(
                error_rate_spikes, key=lambda x: x.errors_per_minute, reverse=True
            ),
            connection_exhaustion=connection_exhaustion,
            total_pods_analyzed=total,
        )

        logger.info(
            "Network Agent: %d saturated, %d chatty, %d error spikes, %d conn exhaust",
            len(saturated_pods), len(chatty_pods),
            len(error_rate_spikes), len(connection_exhaustion),
        )

        return output

    # -------------------------------------------------------------------------
    # Step 1: Network Saturation
    # -------------------------------------------------------------------------

    def _detect_saturation(
        self, df: pd.DataFrame, pod: str, namespace: str
    ) -> list[NetworkSaturationRecord]:
        """Detect rx or tx saturation above threshold."""
        records = []

        for direction, sat_col, rate_col in [
            ("rx", "rx_saturation", "rx_rate"),
            ("tx", "tx_saturation", "tx_rate"),
        ]:
            if sat_col not in df.columns:
                continue

            mean_sat = float(df[sat_col].dropna().mean())
            if mean_sat >= self._sat_threshold:
                mean_rate = float(df[rate_col].dropna().mean()) if rate_col in df.columns else 0.0
                records.append(NetworkSaturationRecord(
                    pod=pod,
                    namespace=namespace,
                    direction=direction,
                    saturation_pct=round(mean_sat * 100, 1),
                    bytes_per_sec=round(mean_rate, 2),
                ))

        return records

    # -------------------------------------------------------------------------
    # Step 2: Chatty Pod Detection
    # -------------------------------------------------------------------------

    def _detect_chatty(
        self, df: pd.DataFrame, pod: str, namespace: str
    ) -> ChattyPodRecord | None:
        """Detect pods with packet rate exceeding threshold."""
        if "rx_packets_rate" not in df.columns:
            return None

        mean_pps = float(df["rx_packets_rate"].dropna().mean())
        if mean_pps >= self._chatty_threshold:
            return ChattyPodRecord(
                pod=pod,
                namespace=namespace,
                packets_per_sec=round(mean_pps, 0),
            )

        return None

    # -------------------------------------------------------------------------
    # Step 3: Log Error Rate Spikes
    # -------------------------------------------------------------------------

    def _detect_error_spike(
        self, summary: dict[str, Any], pod: str, namespace: str
    ) -> ErrorRateRecord | None:
        """Flag pods with error rate above threshold."""
        errors_per_min = summary.get("errors_per_minute", 0.0)

        if errors_per_min >= self._error_threshold:
            return ErrorRateRecord(
                pod=pod,
                namespace=namespace,
                errors_per_minute=round(errors_per_min, 1),
                error_samples=summary.get("error_lines", [])[:5],
            )

        return None

    # -------------------------------------------------------------------------
    # Step 4: Connection Pool Exhaustion
    # -------------------------------------------------------------------------

    def _detect_connection_exhaustion(
        self, summary: dict[str, Any], pod: str, namespace: str
    ) -> ConnectionExhaustionRecord | None:
        """Detect connection exhaustion patterns in logs."""
        conn_errors = summary.get("connection_errors", 0)

        if conn_errors > 0:
            return ConnectionExhaustionRecord(
                pod=pod,
                namespace=namespace,
                connection_error_count=conn_errors,
                sample_lines=summary.get("connection_lines", [])[:3],
            )

        return None
