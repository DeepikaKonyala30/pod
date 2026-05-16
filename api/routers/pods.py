"""
PodMind — API Routers: Pods
"""

from fastapi import APIRouter, Request
from api.models import APIResponse

router = APIRouter()

@router.get("/pods", response_model=APIResponse)
async def get_pods(request: Request):
    """
    Get all monitored pods and their latest metrics.
    """
    redis_reader = request.app.state.redis_reader
    
    pods = await redis_reader.get_pod_metadata()
    
    # We could attach latest CPU/Mem by reading TS.GET from Redis,
    # but for now returning metadata is sufficient for the dashboard list.
    
    return APIResponse(data=pods)
