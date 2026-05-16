"""
PodMind — API Routers: NLP Query

VULN-02 FIX: Input validation and sanitization applied before
passing user queries to the LLM prompt template.
"""

import json
from fastapi import APIRouter, Request
from api.models import APIResponse, NLPQueryRequest, NLPQueryResponse
from config import settings
from intelligence.llm_client import LLMClient
from intelligence.prompt_templates import render_nlp_prompt, NLP_SYSTEM_PROMPT

router = APIRouter()

@router.post("/query", response_model=APIResponse)
async def process_nlp_query(request: Request, query_req: NLPQueryRequest):
    """
    Process natural language questions about the cluster using LLM.

    VULN-02 FIX: Query is validated (max 1000 chars via Pydantic) and
    sanitized in the prompt template renderer before LLM ingestion.
    """
    insight_store = request.app.state.insight_store
    
    # Get cluster context (latest insight + metadata)
    latest = await insight_store.get_latest()
    
    context = ""
    if latest:
        # Build context string
        context_data = {
            "summary": latest.summary,
            "root_causes": [c.model_dump() for c in latest.root_causes],
            "recommendations": [r.model_dump() for r in latest.recommendations],
            "alerts": [a.model_dump() for a in latest.forecast_alerts]
        }
        context = json.dumps(context_data, indent=2, default=str)
    else:
        context = "No recent cluster analysis available."

    # Initialize LLM
    llm = LLMClient(
        tier=settings.llm_tier,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        ollama_host=settings.ollama_host,
        ollama_model=settings.ollama_model,
    )
    
    if not llm.available_tiers:
        return APIResponse(
            data=NLPQueryResponse(
                answer="Natural language query is unavailable (No LLM tiers configured).",
                context_used=False
            ).model_dump()
        )

    # VULN-02 FIX: render_nlp_prompt now sanitizes user input internally
    user_prompt = render_nlp_prompt(user_query=query_req.query, context=context)
    
    answer = await llm.generate_nlp_response(
        system_prompt=NLP_SYSTEM_PROMPT,
        user_query=user_prompt,
        context=context
    )
    
    response = NLPQueryResponse(
        answer=answer,
        context_used=bool(latest)
    )
    
    return APIResponse(data=response.model_dump())
