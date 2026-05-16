"""
PodMind — API Routers: Forecast
"""

from fastapi import APIRouter, Request
from api.models import APIResponse

router = APIRouter()

@router.get("/forecast", response_model=APIResponse)
async def get_forecasts(request: Request):
    """
    Get all active pod forecasts.
    """
    insight_store = request.app.state.insight_store
    
    # Forecasts are stored in the InsightOutput
    latest = await insight_store.get_latest()
    
    if not latest:
        return APIResponse(data=[])
        
    return APIResponse(data=[f.model_dump() for f in latest.forecasts])

@router.get("/forecast/{namespace}/{pod}", response_model=APIResponse)
async def get_pod_forecast(request: Request, namespace: str, pod: str):
    """
    Get forecast for a specific pod.
    """
    insight_store = request.app.state.insight_store
    latest = await insight_store.get_latest()
    
    if not latest:
        return APIResponse(data=None)
        
    # Find specific forecast
    for f in latest.forecasts:
        if f.namespace == namespace and f.pod == pod:
            return APIResponse(data=f.model_dump())
            
    return APIResponse(data=None)
