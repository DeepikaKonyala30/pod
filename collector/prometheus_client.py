"""
PodMind — Prometheus Query Client

Async PromQL query executor that retrieves pod-level CPU, memory, network,
and storage metrics from Prometheus. Returns results as pandas DataFrames
with uniform timestamps for downstream normalization.

Uses PodMind's custom recording rules (podmind:*) for pre-computed derived
metrics when available, falling back to raw container_* metrics.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger("podmind.collector.prometheus")


class PrometheusClient:
    """
    Prometheus HTTP API client for PodMind metric collection.

    Executes PromQL instant and range queries against the Prometheus server,
    returning results as structured dictionaries or pandas DataFrames.
    """

    def __init__(self, prometheus_url: str, timeout: float = 30.0):
        """
        Args:
            prometheus_url: Base URL of the Prometheus server (e.g., http://localhost:9090).
            timeout: HTTP request timeout in seconds.
        """
        self._base_url = prometheus_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )
        logger.info("Prometheus client initialized: %s", self._base_url)

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    # -------------------------------------------------------------------------
    # Core Query Methods
    # -------------------------------------------------------------------------

    async def query_instant(self, promql: str) -> list[dict[str, Any]]:
        """
        Execute a PromQL instant query.

        Returns a list of result dictionaries with 'metric' labels and 'value'.
        """
        try:
            response = await self._client.get(
                "/api/v1/query",
                params={"query": promql},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.error("Prometheus query failed: %s", data.get("error", "unknown"))
                return []

            results = []
            for item in data.get("data", {}).get("result", []):
                metric = item.get("metric", {})
                value = item.get("value", [0, "0"])
                results.append({
                    "metric": metric,
                    "namespace": metric.get("namespace", ""),
                    "pod": metric.get("pod", ""),
                    "container": metric.get("container", ""),
                    "timestamp": float(value[0]),
                    "value": float(value[1]) if value[1] != "NaN" else 0.0,
                })

            return results

        except httpx.HTTPError as e:
            logger.error("Prometheus instant query failed: %s", str(e))
            return []

    async def query_range(
        self,
        promql: str,
        start: float,
        end: float,
        step: str = "5s",
    ) -> dict[str, pd.DataFrame]:
        """
        Execute a PromQL range query, returning DataFrames per pod.

        Args:
            promql: PromQL expression.
            start: Start timestamp (Unix epoch).
            end: End timestamp (Unix epoch).
            step: Query resolution step (default: 5s).

        Returns:
            Dictionary mapping "{namespace}:{pod}" to a DataFrame with
            DatetimeIndex and a 'value' column.
        """
        try:
            response = await self._client.get(
                "/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start,
                    "end": end,
                    "step": step,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.error("Prometheus range query failed: %s", data.get("error", "unknown"))
                return {}

            result_frames = {}
            for series in data.get("data", {}).get("result", []):
                metric = series.get("metric", {})
                ns = metric.get("namespace", "unknown")
                pod = metric.get("pod", "unknown")
                key = f"{ns}:{pod}"

                values = series.get("values", [])
                if not values:
                    continue

                timestamps = [datetime.fromtimestamp(v[0], tz=timezone.utc) for v in values]
                vals = [float(v[1]) if v[1] != "NaN" else np.nan for v in values]

                df = pd.DataFrame({"value": vals}, index=pd.DatetimeIndex(timestamps))
                df.index.name = "timestamp"
                result_frames[key] = df

            return result_frames

        except httpx.HTTPError as e:
            logger.error("Prometheus range query failed: %s", str(e))
            return {}

    # -------------------------------------------------------------------------
    # Pre-Built Metric Queries (PodMind Recording Rules)
    # -------------------------------------------------------------------------

    async def get_cpu_usage_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """
        Get CPU usage percentage (of request) for all pods over a time window.
        Uses the pre-computed podmind:pod_cpu_usage_rate recording rule.
        """
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        # Try pre-computed recording rule first, fall back to raw query
        result = await self.query_range(
            promql='podmind:pod_cpu_usage_rate',
            start=start,
            end=now,
            step="5s",
        )

        if not result:
            logger.info("Recording rule unavailable, using raw PromQL for CPU")
            result = await self.query_range(
                promql=(
                    'sum by (namespace, pod) ('
                    '  rate(container_cpu_usage_seconds_total'
                    '  {container!="", container!="POD"}[1m])'
                    ')'
                ),
                start=start,
                end=now,
                step="5s",
            )

        return result

    async def get_cpu_throttle_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """Get CPU throttle ratio for all pods."""
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        result = await self.query_range(
            promql='podmind:pod_cpu_throttle_ratio',
            start=start,
            end=now,
            step="5s",
        )

        if not result:
            result = await self.query_range(
                promql=(
                    'sum by (namespace, pod) ('
                    '  rate(container_cpu_cfs_throttled_seconds_total{container!=""}[1m])'
                    ')'
                    ' / '
                    'sum by (namespace, pod) ('
                    '  rate(container_cpu_cfs_periods_total{container!=""}[1m])'
                    ')'
                ),
                start=start,
                end=now,
                step="5s",
            )

        return result

    async def get_memory_usage_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """
        Get memory RSS usage for all pods over a time window.
        Returns raw RSS bytes — normalization (ratio to limit) done in normalizer.py.
        """
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        result = await self.query_range(
            promql=(
                'sum by (namespace, pod) ('
                '  container_memory_rss{container!="", container!="POD"}'
                ')'
            ),
            start=start,
            end=now,
            step="5s",
        )

        return result

    async def get_memory_cache_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """Get cache memory for all pods (for cache pressure analysis)."""
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        return await self.query_range(
            promql=(
                'sum by (namespace, pod) ('
                '  container_memory_cache{container!=""}'
                ')'
            ),
            start=start,
            end=now,
            step="5s",
        )

    async def get_memory_limits_all_pods(self) -> dict[str, float]:
        """
        Get memory limits for all pods (instant query).
        Returns: {"namespace:pod": limit_bytes}
        """
        results = await self.query_instant(
            'sum by (namespace, pod) ('
            '  kube_pod_container_resource_limits{resource="memory"}'
            ')'
        )
        return {
            f"{r['namespace']}:{r['pod']}": r["value"]
            for r in results
            if r["pod"]
        }

    async def get_cpu_limits_all_pods(self) -> dict[str, float]:
        """
        Get CPU limits (cores) for all pods (instant query).
        Returns: {"namespace:pod": limit_cores}
        """
        results = await self.query_instant(
            'sum by (namespace, pod) ('
            '  kube_pod_container_resource_limits{resource="cpu"}'
            ')'
        )
        return {
            f"{r['namespace']}:{r['pod']}": r["value"]
            for r in results
            if r["pod"]
        }

    async def get_network_rx_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """Get network receive bytes rate for all pods."""
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        result = await self.query_range(
            promql='podmind:pod_network_rx_bytes_rate',
            start=start,
            end=now,
            step="10s",
        )

        if not result:
            result = await self.query_range(
                promql=(
                    'sum by (namespace, pod) ('
                    '  rate(container_network_receive_bytes_total{interface!="lo"}[1m])'
                    ')'
                ),
                start=start,
                end=now,
                step="10s",
            )

        return result

    async def get_network_tx_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """Get network transmit bytes rate for all pods."""
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        result = await self.query_range(
            promql='podmind:pod_network_tx_bytes_rate',
            start=start,
            end=now,
            step="10s",
        )

        if not result:
            result = await self.query_range(
                promql=(
                    'sum by (namespace, pod) ('
                    '  rate(container_network_transmit_bytes_total{interface!="lo"}[1m])'
                    ')'
                ),
                start=start,
                end=now,
                step="10s",
            )

        return result

    async def get_network_packets_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """Get network receive packet rate for all pods (chatty pod detection)."""
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        return await self.query_range(
            promql=(
                'sum by (namespace, pod) ('
                '  rate(container_network_receive_packets_total{interface!="lo"}[1m])'
                ')'
            ),
            start=start,
            end=now,
            step="10s",
        )

    async def get_fs_write_rate_all_pods(
        self, window_minutes: int = 10
    ) -> dict[str, pd.DataFrame]:
        """Get filesystem write rate for all pods (storage agent)."""
        now = datetime.now(timezone.utc).timestamp()
        start = now - (window_minutes * 60)

        return await self.query_range(
            promql=(
                'sum by (namespace, pod) ('
                '  rate(container_fs_writes_bytes_total{container!=""}[1m])'
                ')'
            ),
            start=start,
            end=now,
            step="10s",
        )

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------

    async def is_healthy(self) -> bool:
        """Check if Prometheus is reachable and healthy."""
        try:
            response = await self._client.get("/-/healthy")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
