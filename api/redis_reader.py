"""
PodMind — API Redis Reader

Provides asynchronous methods to read timeseries metrics, metadata, and
events from Redis. Used by both the REST endpoints and the periodic
agent analysis scheduler.

Reads from Redis TimeSeries module using `TS.RANGE` and standard Redis hashes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd
import redis.asyncio as aioredis

logger = logging.getLogger("podmind.api.redis_reader")


class RedisReader:
    """Reads metric data and cluster metadata from Redis."""

    def __init__(self, redis_url: str):
        self._redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=5.0,
        )

    async def is_healthy(self) -> bool:
        """Check connection to Redis."""
        try:
            return await self._redis.ping()
        except Exception:
            return False

    async def close(self):
        """Close connection."""
        await self._redis.aclose()

    # -------------------------------------------------------------------------
    # Metadata Readers
    # -------------------------------------------------------------------------

    async def get_pod_metadata(self) -> list[dict[str, Any]]:
        """Get all known pods."""
        # Prefer the aggregated key if present, but also support the per-pod
        # hash layout written by RedisWriter.write_pod_metadata().
        data = await self._redis.get("meta:pods")
        if data:
            return json.loads(data)

        pods: list[dict[str, Any]] = []
        async for key in self._redis.scan_iter(match="meta:*:*"):
            if key == "meta:pods" or key == "meta:pvc_mapping":
                continue
            record = await self._redis.hgetall(key)
            if not record:
                continue
            pods.append(record)

        return pods

    async def get_pod_metadata_map(self) -> dict[str, dict[str, Any]]:
        """Get pod metadata mapped by 'namespace:pod' key."""
        pods = await self.get_pod_metadata()
        result = {}
        for pod in pods:
            namespace = pod.get("namespace", "default")
            name = pod.get("name", "")
            if namespace and name:
                result[f"{namespace}:{name}"] = pod
        return result

    async def get_pvc_mapping(self) -> dict[str, list[str]]:
        """Get mapping of namespace:pod -> list of PVC names."""
        data = await self._redis.get("meta:pvc_mapping")
        return json.loads(data) if data else {}

    # -------------------------------------------------------------------------
    # TimeSeries Readers
    # -------------------------------------------------------------------------

    async def _get_ts_range(
        self,
        keys: list[str],
        window_ms: int,
        columns: list[str]
    ) -> dict[str, pd.DataFrame]:
        """
        Helper: fetch TS.RANGE for multiple keys and return as DataFrames.
        """
        if not keys:
            return {}

        now_ms = (await self._redis.time())[0] * 1000
        start_ms = now_ms - window_ms

        pipe = self._redis.pipeline()
        for key in keys:
            # TS.RANGE key from to
            pipe.execute_command("TS.RANGE", key, start_ms, now_ms)
        
        results = await pipe.execute()

        dfs = {}
        for key, ts_data in zip(keys, results):
            if not ts_data:
                continue
            
            # ts_data is list of [timestamp, value]
            idx = [pd.to_datetime(t[0], unit='ms') for t in ts_data]
            vals = [float(t[1]) for t in ts_data]

            df = pd.DataFrame(vals, index=idx, columns=columns)
            # Infer pod key from Redis key e.g. "cpu:default:my-pod" -> "default:my-pod"
            parts = key.split(":", 1)
            pod_key = parts[1] if len(parts) > 1 else key
            dfs[pod_key] = df

        return dfs

    async def get_cpu_data(self, window_minutes: int = 10) -> dict[str, pd.DataFrame]:
        """Fetch CPU usage for all pods."""
        keys = await self._redis.keys("cpu:*")
        return await self._get_ts_range(keys, window_minutes * 60000, ["cpu_usage_pct"])

    async def get_cpu_throttle_data(self, window_minutes: int = 10) -> dict[str, pd.DataFrame]:
        """Fetch CPU throttle ratio for all pods."""
        keys = await self._redis.keys("throttle:*")
        return await self._get_ts_range(keys, window_minutes * 60000, ["throttle_ratio"])

    async def get_memory_data(self, window_minutes: int = 10) -> dict[str, pd.DataFrame]:
        """Fetch memory usage for all pods."""
        keys = await self._redis.keys("mem:*")
        return await self._get_ts_range(keys, window_minutes * 60000, ["memory_usage_ratio"])

    async def get_storage_data(self, window_minutes: int = 10) -> dict[str, pd.DataFrame]:
        """Fetch PVC write bytes per sec."""
        keys = await self._redis.keys("pvc:*")
        return await self._get_ts_range(keys, window_minutes * 60000, ["write_bytes_per_sec"])

    async def get_network_data(self, window_minutes: int = 10) -> dict[str, pd.DataFrame]:
        """Fetch network rx/tx packets and bytes."""
        # For robustness we fetch RX and TX rate series and merge them per pod
        rx_keys = await self._redis.keys("net:rx:*")
        tx_keys = await self._redis.keys("net:tx:*")

        window_ms = window_minutes * 60000

        # Fetch raw series; note: _get_ts_range currently returns dict keys like
        # 'rx:namespace:pod' because it splits on the first ':'. We'll normalize below.
        rx_raw = await self._get_ts_range(rx_keys, window_ms, ["rx_rate"]) if rx_keys else {}
        tx_raw = await self._get_ts_range(tx_keys, window_ms, ["tx_rate"]) if tx_keys else {}

        def normalize_key(k: str, prefix: str) -> str:
            # Convert 'rx:namespace:pod' -> 'namespace:pod'
            if k.startswith(prefix + ":"):
                return k[len(prefix) + 1 :]
            return k

        rx = {normalize_key(k, "rx"): v for k, v in rx_raw.items()}
        tx = {normalize_key(k, "tx"): v for k, v in tx_raw.items()}

        # Merge RX and TX frames per pod (concatenate columns)
        combined: dict[str, pd.DataFrame] = {}
        all_pods = set(rx.keys()) | set(tx.keys())
        for pod in all_pods:
            parts = []
            if pod in rx:
                parts.append(rx[pod])
            if pod in tx:
                parts.append(tx[pod])
            if parts:
                try:
                    combined[pod] = pd.concat(parts, axis=1)
                except Exception:
                    # If concat fails, fall back to first available DF
                    combined[pod] = parts[0]

        return combined

    # -------------------------------------------------------------------------
    # Stream Readers (Events & Logs)
    # -------------------------------------------------------------------------

    async def get_recent_events(self, count: int = 100) -> list[dict[str, Any]]:
        """Read recent Kubernetes events from the stream."""
        try:
            # XREVRANGE to get newest first
            messages = await self._redis.xrevrange("podmind:events", max="+", min="-", count=count)
            events = []
            for _, fields in messages:
                events.append({
                    "namespace": fields.get("namespace", ""),
                    "pod": fields.get("pod", ""),
                    "reason": fields.get("reason", ""),
                    "message": fields.get("message", ""),
                    "type": fields.get("type", "Normal"),
                    "timestamp": fields.get("timestamp", ""),
                })
            return events
        except Exception as e:
            logger.error("Failed to read events: %s", e)
            return []

    async def get_log_summaries(self) -> dict[str, dict[str, Any]]:
        """Get latest log summaries per pod."""
        # Logs are stored in a Hash by pod key
        data = await self._redis.hgetall("logs:latest")
        return {k: json.loads(v) for k, v in data.items()}
