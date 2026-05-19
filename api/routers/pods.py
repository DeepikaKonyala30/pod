"""
PodMind — API Routers: Pods

Returns all monitored pods enriched with latest CPU/memory snapshots.
Falls back to synthetic demo data when Redis is empty.
"""

import asyncio
import logging
from fastapi import APIRouter, Request
from api.models import APIResponse
from api.real_data import get_real_data_status
import api.mock_data as mock

router = APIRouter()
logger = logging.getLogger("podmind.api.pods")


@router.get("/pods", response_model=APIResponse)
async def get_pods(request: Request):
    """
    Get all monitored pods with latest metric snapshots.
    Returns synthetic demo data when Redis is empty (demo/hybrid mode).
    """
    redis_reader = request.app.state.redis_reader
    real_data = await get_real_data_status(redis_reader)

    try:
        pod_metadata = await asyncio.wait_for(redis_reader.get_pod_metadata(), timeout=3.0)
    except Exception as e:
        logger.warning("Failed to read pod metadata from Redis: %s", e)
        pod_metadata = []

    if not pod_metadata:
        # Demo mode — return synthetic pods
        if real_data.ready:
            return APIResponse(data=[])
        return APIResponse(data=mock.get_demo_pods())

    # Enrich with latest metric snapshots from Redis TimeSeries (TS.GET = last value)
    import datetime as dt_module
    now = dt_module.datetime.now(dt_module.timezone.utc).isoformat()
    enriched = []

    try:
        redis = redis_reader._redis
        pipe = redis.pipeline()
        for pod in pod_metadata:
            ns = pod.get("namespace", "default")
            name = pod.get("name", "")
            key = f"{ns}:{name}"
            pipe.execute_command("TS.GET", f"cpu:{key}")
            pipe.execute_command("TS.GET", f"mem:{key}")

        results = await asyncio.wait_for(pipe.execute(), timeout=5.0)

        for i, pod in enumerate(pod_metadata):
            cpu_result = results[i * 2]
            mem_result = results[i * 2 + 1]
            cpu_pct = float(cpu_result[1]) if cpu_result else 0.0
            mem_ratio = float(mem_result[1]) if mem_result else 0.0
            status = (
                "critical" if (cpu_pct > 85 or mem_ratio > 0.88) else
                "warning" if (cpu_pct > 65 or mem_ratio > 0.70) else
                "healthy"
            )
            enriched.append({
                **pod,
                "cpu_pct": round(cpu_pct, 2),
                "memory_ratio": round(mem_ratio, 4),
                "status": status,
                "collected_at": now,
            })
    except Exception as e:
        logger.warning("Failed to enrich pod metrics: %s — returning base metadata", e)
        for pod in pod_metadata:
            enriched.append({**pod, "cpu_pct": 0.0, "memory_ratio": 0.0,
                             "status": "healthy", "collected_at": now})

    # If still empty, fall back to synthetic
    if not enriched:
        if real_data.ready:
            return APIResponse(data=[])
        return APIResponse(data=mock.get_demo_pods())

    return APIResponse(data=enriched)
