"""
Runtime readiness checks for deciding whether demo fallback data is allowed.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
from kubernetes import client, config

from config import settings


@dataclass(frozen=True)
class RealDataStatus:
    redis: bool
    prometheus: bool
    kubernetes: bool

    @property
    def ready(self) -> bool:
        return self.redis and self.prometheus and self.kubernetes


_cached_status: RealDataStatus | None = None
_cached_at = 0.0
_cache_lock = asyncio.Lock()
_cache_ttl_seconds = 10.0


async def get_real_data_status(redis_reader, *, use_cache: bool = True) -> RealDataStatus:
    """Return dependency readiness for real collector-backed data."""
    global _cached_status, _cached_at

    now = time.monotonic()
    if use_cache and _cached_status and now - _cached_at < _cache_ttl_seconds:
        return _cached_status

    async with _cache_lock:
        now = time.monotonic()
        if use_cache and _cached_status and now - _cached_at < _cache_ttl_seconds:
            return _cached_status

        redis_ok, prometheus_ok, kubernetes_ok = await asyncio.gather(
            _check_redis(redis_reader),
            _check_prometheus(),
            _check_kubernetes(),
        )
        _cached_status = RealDataStatus(
            redis=redis_ok,
            prometheus=prometheus_ok,
            kubernetes=kubernetes_ok,
        )
        _cached_at = time.monotonic()
        return _cached_status


async def _check_redis(redis_reader) -> bool:
    try:
        return bool(await redis_reader.is_healthy())
    except Exception:
        return False


async def _check_prometheus() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            response = await http.get(f"{settings.prometheus_url.rstrip('/')}/-/healthy")
        return response.status_code == 200
    except Exception:
        return False


async def _check_kubernetes() -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _check_kubernetes_sync)


def _check_kubernetes_sync() -> bool:
    try:
        if settings.k8s_in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config(config_file=settings.kubeconfig)
        api = client.CoreV1Api()
        api.list_namespace(watch=False, timeout_seconds=5)
        return True
    except Exception:
        return False
