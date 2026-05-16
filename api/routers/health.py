"""
PodMind — API Routers: Health Check
"""

from fastapi import APIRouter, Request
from api.models import SystemHealth
from config import settings
from intelligence.llm_client import LLMClient

router = APIRouter()

@router.get("/health", response_model=SystemHealth)
async def health_check(request: Request):
    """
    Check system health, Redis connection, and LLM availability.
    """
    redis_reader = request.app.state.redis_reader
    redis_ok = await redis_reader.is_healthy()
    
    # We can briefly initialize LLMClient to check configured tiers
    # (or store it in app state if preferred)
    llm = LLMClient(
        tier=settings.llm_tier,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        ollama_host=settings.ollama_host,
        ollama_model=settings.ollama_model,
    )
    
    status = "healthy" if redis_ok else "degraded"
    if not redis_ok:
        status = "unhealthy"
        
    return SystemHealth(
        status=status,
        redis_connected=redis_ok,
        prometheus_connected=True, # Prometheus is handled by Collector
        llm_tiers_available=llm.available_tiers
    )
