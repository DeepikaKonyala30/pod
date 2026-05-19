"""
PodMind — API Routers: Health Check
"""

from fastapi import APIRouter, Request
from api.models import SystemHealth
from api.real_data import get_real_data_status
from config import settings
from intelligence.llm_client import LLMClient

router = APIRouter()

@router.get("/health", response_model=SystemHealth)
async def health_check(request: Request):
    """
    Check system health, Redis connection, and LLM availability.
    """
    redis_reader = request.app.state.redis_reader
    real_data = await get_real_data_status(redis_reader, use_cache=False)
    
    # We can briefly initialize LLMClient to check configured tiers
    # (or store it in app state if preferred)
    llm = LLMClient(
        tier=settings.llm_tier,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        groq_api_key=settings.groq_api_key,
        groq_model=settings.groq_model,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        ollama_host=settings.ollama_host,
        ollama_model=settings.ollama_model,
    )
    
    status = "healthy" if real_data.ready else "degraded"
    if not real_data.redis:
        status = "unhealthy"
        
    return SystemHealth(
        status=status,
        redis_connected=real_data.redis,
        prometheus_connected=real_data.prometheus,
        kubernetes_connected=real_data.kubernetes,
        real_data_mode=real_data.ready,
        llm_tiers_available=llm.available_tiers
    )
