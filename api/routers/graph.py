"""
PodMind — API Routers: Dependency Graph
"""

from fastapi import APIRouter, Request
from api.models import APIResponse

router = APIRouter()

@router.get("/graph", response_model=APIResponse)
async def get_dependency_graph(request: Request):
    """
    Get the latest Granger causality dependency graph.
    """
    insight_store = request.app.state.insight_store
    
    # The dependency graph is stored inside the InsightOutput
    latest = await insight_store.get_latest()
    
    if not latest:
        return APIResponse(data={"nodes": [], "edges": []})
        
    return APIResponse(data=latest.dependency_graph.model_dump())
