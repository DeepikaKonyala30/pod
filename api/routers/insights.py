"""
PodMind — API Routers: Insights
"""

from fastapi import APIRouter, Request, HTTPException
from api.models import APIResponse, InsightHistoryResponse

router = APIRouter()

@router.get("/insights/latest", response_model=APIResponse)
async def get_latest_insight(request: Request):
    """Get the most recent LLM-generated insight."""
    insight_store = request.app.state.insight_store
    latest = await insight_store.get_latest()
    
    if not latest:
        return APIResponse(data=None, error="No insights available yet")
        
    return APIResponse(data=latest.model_dump())

@router.get("/insights/history", response_model=InsightHistoryResponse)
async def get_insight_history(request: Request, limit: int = 10):
    """Get recent history of insights."""
    insight_store = request.app.state.insight_store
    history = await insight_store.get_history_with_summaries(limit=limit)
    count = await insight_store.count()
    
    return InsightHistoryResponse(history=history, total_count=count)

@router.get("/insights/{insight_id}", response_model=APIResponse)
async def get_insight_by_id(request: Request, insight_id: str):
    """Get a specific insight by ID."""
    insight_store = request.app.state.insight_store
    insight = await insight_store.get_by_id(insight_id)
    
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
        
    return APIResponse(data=insight.model_dump())
