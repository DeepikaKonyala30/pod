"""
PodMind — API Routers: PVCs
"""

from fastapi import APIRouter, Request
from api.models import APIResponse

router = APIRouter()

@router.get("/pvcs", response_model=APIResponse)
async def get_pvcs(request: Request):
    """
    Get all PVCs and their pod mappings.
    """
    redis_reader = request.app.state.redis_reader
    
    mapping = await redis_reader.get_pvc_mapping()
    
    return APIResponse(data=mapping)
