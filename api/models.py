"""
PodMind — API Pydantic Models

Response schemas for the FastAPI endpoints.
Many endpoints return the core schemas defined in `agents/schemas.py`.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

from agents.schemas import InsightOutput, DependencyGraph, PodForecast


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool = True
    data: Any
    error: Optional[str] = None


class SystemHealth(BaseModel):
    """System health status."""
    status: str
    redis_connected: bool
    prometheus_connected: bool
    kubernetes_connected: bool = False
    real_data_mode: bool = False
    llm_tiers_available: list[str]


class InsightHistoryResponse(BaseModel):
    """Response model for insight history list."""
    history: list[dict[str, Any]]
    total_count: int


class NLPQueryRequest(BaseModel):
    """Request model for natural language queries."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question about cluster health (1-1000 chars)",
    )


class NLPQueryResponse(BaseModel):
    """Response model for natural language queries."""
    answer: str
    context_used: bool
