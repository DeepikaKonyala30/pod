"""
PodMind — Redis TimeSeries & Stream Writer

Writes normalized metrics to Redis TimeSeries for agent consumption
and publishes events to Redis Streams for the agent event bus.

Key schema (per SRS §5.2.3):
  - cpu:{namespace}:{pod}       → CPU usage percentage (TS)
  - mem:{namespace}:{pod}       → Memory usage ratio (TS)
  - net:{namespace}:{pod}       → Network rx/tx rates (TS)
  - pvc:{namespace}:{pvc}       → PVC IOPS/throughput (TS)
  - event:{namespace}:{pod}:{ts} → Pod events (String)
  - meta:{namespace}:{pod}      → Pod metadata (Hash)

All TimeSeries keys have 24-hour retention with namespace/pod labels
for efficient filtering via TS.MRANGE.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
import redis.asyncio as aioredis
from redis.exceptions import ResponseError

logger = logging.getLogger("podmind.collector.redis_writer")


class RedisWriter:
    """
    Writes PodMind metrics to Redis TimeSeries and Streams.

    Handles:
      - TimeSeries key creation with labels and retention
      - Batch metric writes (TS.ADD)
      - Pod metadata storage (HSET)
      - Event publishing to Redis Streams (XADD)
      - Graceful handling of existing keys
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        retention_ms: int = 86_400_000,  # 24 hours
        max_connections: int = 20,
    ):
        """
        Args:
            redis_url: Redis connection URL.
            retention_ms: TimeSeries data retention in milliseconds.
            max_connections: Maximum Redis connection pool size.
        """
        self._redis_url = redis_url
        self._retention_ms = retention_ms
        self._pool = aioredis.ConnectionPool.from_url(
            redis_url,
            max_connections=max_connections,
            decode_responses=True,
        )
        self._redis = aioredis.Redis(connection_pool=self._pool)
        self._created_keys: set[str] = set()  # Track created TS keys to avoid re-creation

    async def close(self):
        """Close the Redis connection pool."""
        await self._redis.aclose()
        await self._pool.disconnect()

    # -------------------------------------------------------------------------
    # TimeSeries Key Management
    # -------------------------------------------------------------------------

    async def _ensure_ts_key(
        self,
        key: str,
        labels: dict[str, str],
    ) -> None:
        """
        Ensure a TimeSeries key exists with the correct retention and labels.
        Uses local cache to avoid redundant TS.CREATE calls.
        """
        if key in self._created_keys:
            return

        try:
            await self._redis.execute_command(
                "TS.CREATE",
                key,
                "RETENTION",
                self._retention_ms,
                "LABELS",
                *[item for pair in labels.items() for item in pair],
            )
            logger.debug("Created TimeSeries key: %s", key)
        except ResponseError as e:
            if "already exists" not in str(e).lower():
                logger.error("Failed to create TS key %s: %s", key, str(e))
                return

        self._created_keys.add(key)

    # -------------------------------------------------------------------------
    # CPU Metric Writing
    # -------------------------------------------------------------------------

    async def write_cpu_metrics(
        self,
        normalized_cpu: dict[str, pd.DataFrame],
    ) -> int:
        """
        Write normalized CPU usage to Redis TimeSeries.

        Args:
            normalized_cpu: {"ns:pod": DataFrame with 'cpu_usage_pct'}.

        Returns:
            Number of data points written.
        """
        count = 0
        pipe = self._redis.pipeline()

        for key, df in normalized_cpu.items():
            if df.empty or "cpu_usage_pct" not in df.columns:
                continue

            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            namespace, pod = parts

            ts_key = f"cpu:{namespace}:{pod}"
            await self._ensure_ts_key(ts_key, {
                "namespace": namespace,
                "pod": pod,
                "type": "cpu",
            })

            for timestamp, row in df.iterrows():
                ts_ms = int(timestamp.timestamp() * 1000)
                value = float(row["cpu_usage_pct"])
                if not np.isnan(value):
                    pipe.execute_command("TS.ADD", ts_key, ts_ms, round(value, 6))
                    count += 1

        try:
            await pipe.execute()
        except ResponseError as e:
            logger.warning("Batch CPU write error (some points may be duplicates): %s", str(e))

        logger.debug("Wrote %d CPU data points", count)
        return count

    # -------------------------------------------------------------------------
    # Memory Metric Writing
    # -------------------------------------------------------------------------

    async def write_memory_metrics(
        self,
        normalized_memory: dict[str, pd.DataFrame],
    ) -> int:
        """Write normalized memory usage ratios to Redis TimeSeries."""
        count = 0
        pipe = self._redis.pipeline()

        for key, df in normalized_memory.items():
            if df.empty or "memory_usage_ratio" not in df.columns:
                continue

            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            namespace, pod = parts

            ts_key = f"mem:{namespace}:{pod}"
            await self._ensure_ts_key(ts_key, {
                "namespace": namespace,
                "pod": pod,
                "type": "memory",
            })

            for timestamp, row in df.iterrows():
                ts_ms = int(timestamp.timestamp() * 1000)
                value = float(row["memory_usage_ratio"])
                if not np.isnan(value):
                    pipe.execute_command("TS.ADD", ts_key, ts_ms, round(value, 6))
                    count += 1

        try:
            await pipe.execute()
        except ResponseError as e:
            logger.warning("Batch memory write error: %s", str(e))

        logger.debug("Wrote %d memory data points", count)
        return count

    # -------------------------------------------------------------------------
    # Network Metric Writing
    # -------------------------------------------------------------------------

    async def write_network_metrics(
        self,
        normalized_network: dict[str, pd.DataFrame],
    ) -> int:
        """Write normalized network metrics (rx/tx rates) to Redis TimeSeries."""
        count = 0
        pipe = self._redis.pipeline()

        for key, df in normalized_network.items():
            if df.empty:
                continue

            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            namespace, pod = parts

            # Write rx rate
            if "rx_rate" in df.columns:
                ts_key = f"net:rx:{namespace}:{pod}"
                await self._ensure_ts_key(ts_key, {
                    "namespace": namespace,
                    "pod": pod,
                    "type": "network",
                    "direction": "rx",
                })
                for timestamp, row in df.iterrows():
                    ts_ms = int(timestamp.timestamp() * 1000)
                    value = float(row["rx_rate"])
                    if not np.isnan(value):
                        pipe.execute_command("TS.ADD", ts_key, ts_ms, round(value, 2))
                        count += 1

            # Write tx rate
            if "tx_rate" in df.columns:
                ts_key = f"net:tx:{namespace}:{pod}"
                await self._ensure_ts_key(ts_key, {
                    "namespace": namespace,
                    "pod": pod,
                    "type": "network",
                    "direction": "tx",
                })
                for timestamp, row in df.iterrows():
                    ts_ms = int(timestamp.timestamp() * 1000)
                    value = float(row["tx_rate"])
                    if not np.isnan(value):
                        pipe.execute_command("TS.ADD", ts_key, ts_ms, round(value, 2))
                        count += 1

        try:
            await pipe.execute()
        except ResponseError as e:
            logger.warning("Batch network write error: %s", str(e))

        logger.debug("Wrote %d network data points", count)
        return count

    # -------------------------------------------------------------------------
    # Storage Metric Writing
    # -------------------------------------------------------------------------

    async def write_storage_metrics(
        self,
        normalized_storage: dict[str, pd.DataFrame],
    ) -> int:
        """Write normalized PVC/storage metrics to Redis TimeSeries."""
        count = 0
        pipe = self._redis.pipeline()

        for key, df in normalized_storage.items():
            if df.empty:
                continue

            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            namespace, pod = parts

            if "write_bytes_per_sec" in df.columns:
                ts_key = f"pvc:{namespace}:{pod}"
                await self._ensure_ts_key(ts_key, {
                    "namespace": namespace,
                    "pod": pod,
                    "type": "storage",
                })
                for timestamp, row in df.iterrows():
                    ts_ms = int(timestamp.timestamp() * 1000)
                    value = float(row["write_bytes_per_sec"])
                    if not np.isnan(value):
                        pipe.execute_command("TS.ADD", ts_key, ts_ms, round(value, 2))
                        count += 1

        try:
            await pipe.execute()
        except ResponseError as e:
            logger.warning("Batch storage write error: %s", str(e))

        logger.debug("Wrote %d storage data points", count)
        return count

    # -------------------------------------------------------------------------
    # Pod Metadata Writing (Hash)
    # -------------------------------------------------------------------------

    async def write_pod_metadata(self, pods: list[dict[str, Any]]) -> int:
        """
        Write pod metadata to Redis Hashes (overwritten each cycle).
        Key pattern: meta:{namespace}:{pod}
        """
        count = 0
        pipe = self._redis.pipeline()

        def _clean(value: Any) -> str:
            """Convert Redis hash values to safe strings; Redis hashes cannot store None."""
            if value is None:
                return ""
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return str(value)

        for pod in pods:
            namespace = _clean(pod.get("namespace")) or "default"
            name = _clean(pod.get("name"))
            meta_key = f"meta:{namespace}:{name}"
            # Serialize complex fields to JSON
            metadata = {
                "name": name,
                "namespace": namespace,
                "phase": _clean(pod.get("phase", "Unknown")) or "Unknown",
                "node_name": _clean(pod.get("node_name")),
                "owner": _clean(pod.get("owner")),
                "owner_kind": _clean(pod.get("owner_kind")),
                "containers": _clean(pod.get("containers", [])),
                "labels": _clean(pod.get("labels", {})),
                "cpu_request": _clean(pod.get("cpu_request", 0)),
                "cpu_limit": _clean(pod.get("cpu_limit", 0)),
                "mem_request": _clean(pod.get("mem_request", 0)),
                "mem_limit": _clean(pod.get("mem_limit", 0)),
                "restart_count": _clean(pod.get("restart_count", 0)),
                "pvc_names": _clean(pod.get("pvc_names", [])),
                "has_resource_limits": _clean(pod.get("has_resource_limits", False)),
                "start_time": _clean(pod.get("start_time")),
                "collected_at": _clean(pod.get("collected_at")),
            }
            pipe.hset(meta_key, mapping=metadata)
            pipe.expire(meta_key, 3600)  # 1 hour TTL (refreshed every 30s)
            count += 1

        await pipe.execute()
        logger.debug("Wrote metadata for %d pods", count)
        return count

    # -------------------------------------------------------------------------
    # Event Publishing (Redis Streams)
    # -------------------------------------------------------------------------

    async def publish_events(
        self,
        events: list[dict[str, Any]],
        stream_key: str = "podmind:events",
    ) -> int:
        """
        Publish pod events to a Redis Stream for agent consumption.

        The stream is trimmed to keep the last 10,000 entries.
        """
        count = 0
        for event in events:
            await self._redis.xadd(
                stream_key,
                {
                    "type": event.get("type", ""),
                    "reason": event.get("reason", ""),
                    "namespace": event.get("namespace", ""),
                    "pod": event.get("involved_object_name", ""),
                    "message": (event.get("message", "") or "")[:500],
                    "timestamp": event.get("timestamp", ""),
                    "is_restart": str(event.get("is_restart", False)),
                    "is_oom": str(event.get("is_oom", False)),
                },
                maxlen=10000,
            )
            count += 1

        if count:
            logger.debug("Published %d events to stream %s", count, stream_key)
        return count

    async def publish_log_summaries(
        self,
        log_summaries: dict[str, dict[str, Any]],
        stream_key: str = "podmind:logs",
    ) -> int:
        """Publish log summaries to Redis Stream for the Network/Log Agent."""
        count = 0
        for key, summary in log_summaries.items():
            await self._redis.xadd(
                stream_key,
                {
                    "pod_key": key,
                    "error_count": str(summary.get("error_count", 0)),
                    "warn_count": str(summary.get("warn_count", 0)),
                    "connection_errors": str(summary.get("connection_errors", 0)),
                    "oom_signals": str(summary.get("oom_signals", 0)),
                    "errors_per_minute": str(summary.get("errors_per_minute", 0)),
                    "has_connection_exhaustion": str(
                        summary.get("has_connection_exhaustion", False)
                    ),
                    "error_lines": json.dumps(summary.get("error_lines", [])[:5]),
                },
                maxlen=5000,
            )
            count += 1

        return count

    # -------------------------------------------------------------------------
    # Read Utilities (for agents)
    # -------------------------------------------------------------------------

    async def read_ts_range(
        self,
        key: str,
        start: str = "-",
        end: str = "+",
        count: Optional[int] = None,
        aggregation: Optional[tuple[str, int]] = None,
    ) -> list[tuple[int, float]]:
        """
        Read a TimeSeries range.

        Args:
            key: TimeSeries key.
            start: Start timestamp ("-" for oldest).
            end: End timestamp ("+" for newest).
            count: Max number of samples.
            aggregation: Tuple of (aggregation_type, bucket_size_ms).

        Returns:
            List of (timestamp_ms, value) tuples.
        """
        args = ["TS.RANGE", key, start, end]
        if count:
            args.extend(["COUNT", count])
        if aggregation:
            args.extend(["AGGREGATION", aggregation[0], aggregation[1]])

        try:
            result = await self._redis.execute_command(*args)
            return [(int(ts), float(val)) for ts, val in result]
        except ResponseError as e:
            logger.warning("TS.RANGE failed for %s: %s", key, str(e))
            return []

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------

    async def is_healthy(self) -> bool:
        """Check if Redis is reachable and TimeSeries module is loaded."""
        try:
            pong = await self._redis.ping()
            if not pong:
                return False
            # Verify TimeSeries module is available
            modules = await self._redis.execute_command("MODULE", "LIST")
            module_names = [m[1] if isinstance(m, list) else "" for m in modules]
            return any("timeseries" in str(name).lower() for name in module_names)
        except Exception:
            return False
