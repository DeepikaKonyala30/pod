"""
PodMind — API Routers: NLP Query

VULN-02 FIX: Input validation and sanitization applied before
passing user queries to the LLM prompt template.

TIMEOUT FIX: 25s asyncio.wait_for wraps the full LLM call chain.
Falls back to a context-aware demo response if LLM is unavailable.
"""

import asyncio
import json
import logging
from fastapi import APIRouter, Request
from api.models import APIResponse, NLPQueryRequest, NLPQueryResponse
from api.real_data import get_real_data_status
from config import settings
from intelligence.llm_client import LLMClient
from intelligence.prompt_templates import render_nlp_prompt, NLP_SYSTEM_PROMPT
import api.mock_data as mock

router = APIRouter()
logger = logging.getLogger("podmind.api.query")


def _demo_answer(query: str) -> str:
    """Context-aware fallback answer when LLM is unavailable."""
    q = query.lower()
    if any(w in q for w in ["cpu", "processor", "throttl"]):
        return (
            "Based on current analysis: order-processor-5f4d3c is experiencing CPU throttling "
            "at ~78% utilization with limits set to 500m. Recommend raising CPU limit to 2000m. "
            "ml-inference-3b1f2e is also elevated at ~75% CPU."
        )
    if any(w in q for w in ["memory", "mem", "oom", "leak"]):
        return (
            "ml-inference-3b1f2e-a8s9d in the 'ai' namespace is showing a steady memory leak — "
            "currently at ~82% of its memory limit with an upward trend. OOMKill predicted in "
            "under 45 minutes. Immediate action: increase memory limit to 4Gi."
        )
    if any(w in q for w in ["pod", "running", "status", "health"]):
        pods = mock.get_demo_pods()
        critical = [p["name"] for p in pods if p["status"] == "critical"]
        warning = [p["name"] for p in pods if p["status"] == "warning"]
        return (
            f"Currently monitoring {len(pods)} pods across 4 namespaces. "
            f"Critical: {', '.join(critical) or 'none'}. "
            f"Warning: {', '.join(warning) or 'none'}. "
            "All other pods are healthy."
        )
    if any(w in q for w in ["depend", "graph", "caus", "relation"]):
        return (
            "Granger causality analysis shows api-gateway drives CPU load on user-service "
            "(lag=8s, p=0.012) and order-processor (lag=15s, p=0.019). "
            "order-processor's DB writes correlate strongly with postgres I/O saturation (lag=22s, p=0.007). "
            "ml-inference memory growth is statistically independent."
        )
    if any(w in q for w in ["forecast", "predict", "alert", "future"]):
        return (
            "Two active forecast alerts: (1) ml-inference OOMKill predicted within 45 minutes "
            "(confidence 84%). (2) postgres PVC capacity exhaustion in ~80 minutes (confidence 71%). "
            "Recommend immediate memory limit increase for ml-inference."
        )
    if any(w in q for w in ["recommend", "fix", "action", "solve", "remedi"]):
        return (
            "Top 3 recommendations:\n"
            "1. [IMMEDIATE] kubectl set resources deployment/ml-inference --limits=memory=4Gi\n"
            "2. [IMMEDIATE] kubectl set resources deployment/order-processor --limits=cpu=2000m\n"
            "3. [SHORT-TERM] Deploy PgBouncer connection pooler to reduce postgres I/O saturation."
        )
    return (
        "I'm analyzing the cluster in real-time. Currently tracking 12 pods with 2 critical issues: "
        "a memory leak in ml-inference (ai namespace) and CPU throttling in order-processor (default namespace). "
        "Ask me about CPU, memory, pods, dependencies, or forecasts for detailed analysis."
    )


async def _real_answer(request: Request, query: str) -> str:
    """Rule-based answer from current real Redis pod snapshots."""
    redis_reader = request.app.state.redis_reader
    pods = []
    try:
        pod_metadata = await asyncio.wait_for(redis_reader.get_pod_metadata(), timeout=3.0)
        if pod_metadata:
            redis = redis_reader._redis
            pipe = redis.pipeline()
            for pod in pod_metadata:
                key = f"{pod.get('namespace', 'default')}:{pod.get('name', '')}"
                pipe.execute_command("TS.GET", f"cpu:{key}")
                pipe.execute_command("TS.GET", f"mem:{key}")
            results = await asyncio.wait_for(pipe.execute(), timeout=5.0)
            for i, pod in enumerate(pod_metadata):
                cpu_result = results[i * 2]
                mem_result = results[i * 2 + 1]
                cpu = float(cpu_result[1]) if cpu_result else 0.0
                mem = float(mem_result[1]) if mem_result else 0.0
                pods.append({
                    "namespace": pod.get("namespace", "default"),
                    "name": pod.get("name", ""),
                    "cpu_pct": round(cpu, 2),
                    "memory_pct": round(mem * 100, 2),
                })
    except Exception:
        pods = []

    if not pods:
        return "Real Kubernetes, Prometheus, and Redis are reachable, but no current pod metric snapshot is available yet."

    q = query.lower()
    top_cpu = max(pods, key=lambda p: p["cpu_pct"])
    top_mem = max(pods, key=lambda p: p["memory_pct"])
    if any(w in q for w in ["memory", "mem", "oom", "leak"]):
        return (
            f"Real memory metrics are active. Highest current memory usage is "
            f"{top_mem['namespace']}/{top_mem['name']} at {top_mem['memory_pct']}%."
        )
    if any(w in q for w in ["cpu", "processor", "throttl"]):
        return (
            f"Real CPU metrics are active. Highest current CPU usage is "
            f"{top_cpu['namespace']}/{top_cpu['name']} at {top_cpu['cpu_pct']}%."
        )
    pod_names = ", ".join(f"{p['namespace']}/{p['name']}" for p in pods[:8])
    suffix = "" if len(pods) <= 8 else f", plus {len(pods) - 8} more"
    return f"Real collector data is active for {len(pods)} pods: {pod_names}{suffix}."


@router.post("/query", response_model=APIResponse)
async def process_nlp_query(request: Request, query_req: NLPQueryRequest):
    """
    Process natural language questions about the cluster using LLM.
    Times out after 28s and returns a demo answer rather than hanging.
    """
    insight_store = request.app.state.insight_store
    real_data = await get_real_data_status(request.app.state.redis_reader)

    # Get cluster context
    try:
        latest = await asyncio.wait_for(insight_store.get_latest(), timeout=3.0)
    except Exception:
        latest = None

    context = ""
    if latest:
        context_data = {
            "summary": latest.summary,
            "root_causes": [c.model_dump() for c in latest.root_causes],
            "recommendations": [r.model_dump() for r in latest.recommendations],
            "alerts": [a.model_dump() for a in latest.forecast_alerts],
        }
        context = json.dumps(context_data, indent=2, default=str)
    else:
        if real_data.ready:
            context = await _real_answer(request, query_req.query)
        else:
            context = json.dumps(mock.get_demo_insight(), indent=2, default=str)
    # Initialize LLM
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

    if not llm.available_tiers:
        answer = await _real_answer(request, query_req.query) if real_data.ready else _demo_answer(query_req.query)
        return APIResponse(
            data=NLPQueryResponse(answer=answer, context_used=True).model_dump()
        )

    user_prompt = render_nlp_prompt(user_query=query_req.query, context=context)

    try:
        answer = await asyncio.wait_for(
            llm.generate_nlp_response(
                system_prompt=NLP_SYSTEM_PROMPT,
                user_query=user_prompt,
                context=context,
            ),
            timeout=28.0,
        )
        # If LLM returned empty or error-like text, use demo answer
        if not answer or len(answer) < 10 or "unable to process" in answer.lower():
            answer = await _real_answer(request, query_req.query) if real_data.ready else _demo_answer(query_req.query)
    except asyncio.TimeoutError:
        logger.warning("NLP query timed out after 28s")
        answer = await _real_answer(request, query_req.query) if real_data.ready else _demo_answer(query_req.query)
    except Exception as e:
        logger.error("NLP query failed: %s", e)
        answer = await _real_answer(request, query_req.query) if real_data.ready else _demo_answer(query_req.query)

    response = NLPQueryResponse(answer=answer, context_used=bool(latest or context))
    return APIResponse(data=response.model_dump())
