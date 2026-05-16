"""
PodMind — API Background Scheduler

Runs the intelligence analysis cycle every 30 seconds.
1. Reads 10m window of metrics from Redis TimeSeries
2. Executes the LangGraph agent orchestrator
3. Passes summary to the Tiered LLM Client
4. Post-processes with Recommendation Engine
5. Persists to Insight Store
6. Broadcasts via WebSocket
"""

import asyncio
import logging
from typing import Optional

from config import settings
from api.redis_reader import RedisReader
from api.websocket import ws_manager
from agents.orchestrator import AgentOrchestrator
from intelligence.llm_client import LLMClient
from intelligence.prompt_templates import render_analysis_prompt, ANALYSIS_SYSTEM_PROMPT
from intelligence.recommendation_engine import RecommendationEngine
from intelligence.insight_store import InsightStore

logger = logging.getLogger("podmind.api.scheduler")


class AnalysisScheduler:
    """Manages the periodic AI analysis execution."""

    def __init__(self, redis_reader: RedisReader, insight_store: InsightStore):
        self._redis = redis_reader
        self._store = insight_store
        
        self._orchestrator = AgentOrchestrator(
            contamination=0.1,
            granger_max_lag=6,
            granger_p_threshold=0.05,
            forecast_horizon_minutes=60,
        )
        self._llm = LLMClient(
            tier=settings.llm_tier,
            anthropic_api_key=settings.anthropic_api_key,
            openai_api_key=settings.openai_api_key,
            ollama_host=settings.ollama_host,
            ollama_model=settings.ollama_model,
        )
        self._recommendations = RecommendationEngine()
        
        self._task: Optional[asyncio.Task] = None
        self._is_running = False

    async def start(self):
        """Start the background analysis loop."""
        if self._is_running:
            return
        
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Analysis scheduler started (Interval: 30s)")

    async def stop(self):
        """Stop the background analysis loop."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Analysis scheduler stopped")

    async def _run_loop(self):
        """The main loop that triggers analysis every 30 seconds."""
        while self._is_running:
            try:
                await self.run_analysis_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in analysis loop: %s", str(e), exc_info=True)
            
            # Wait 30 seconds before next cycle
            await asyncio.sleep(30)

    async def run_analysis_cycle(self):
        """Execute a single complete analysis cycle."""
        logger.info("Starting intelligence analysis cycle...")

        # 1. Read 10-minute metrics window from Redis
        cpu_data = await self._redis.get_cpu_data(window_minutes=10)
        cpu_throttle = await self._redis.get_cpu_throttle_data(window_minutes=10)
        memory_data = await self._redis.get_memory_data(window_minutes=10)
        storage_data = await self._redis.get_storage_data(window_minutes=10)
        network_data = await self._redis.get_network_data(window_minutes=10)
        
        log_summaries = await self._redis.get_log_summaries()
        events = await self._redis.get_recent_events(count=50)
        pvc_mapping = await self._redis.get_pvc_mapping()
        pod_metadata = await self._redis.get_pod_metadata()

        if not cpu_data:
            logger.warning("No CPU data found in Redis. Skipping analysis cycle.")
            return

        # 2. Run Multi-Agent Orchestrator (LangGraph)
        analysis_output = await self._orchestrator.run_analysis_cycle(
            cpu_data=cpu_data,
            cpu_throttle=cpu_throttle,
            memory_data=memory_data,
            storage_data=storage_data,
            network_data=network_data,
            log_summaries=log_summaries,
            events=events,
            pod_pvc_mapping=pvc_mapping,
            pod_metadata=pod_metadata,
        )

        # 3. Get LLM Insights
        summary_dict = self._orchestrator.get_agent_summary(analysis_output)
        prompt = render_analysis_prompt(summary_dict)
        
        logger.info("Generating LLM insights...")
        raw_insight = await self._llm.generate(
            system_prompt=ANALYSIS_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
        
        # If LLM failed entirely, fallback to rule engine
        if not raw_insight or "LLM analysis unavailable" in raw_insight.summary:
            logger.warning("LLM generation failed, using rule-based fallback")
            from intelligence.rule_engine import RuleEngine
            raw_insight = RuleEngine().generate(analysis_output)

        # 4. Post-process recommendations
        final_insight = self._recommendations.process(raw_insight)

        # 5. Persist to Redis
        insight_id = await self._store.store_insight(final_insight)
        logger.info("Analysis cycle complete. Insight ID: %s", insight_id)

        # 6. Broadcast via WebSocket
        await ws_manager.broadcast({
            "type": "NEW_INSIGHT",
            "data": final_insight.model_dump(mode="json"),
            "graph": analysis_output.dependency_graph.model_dump(mode="json"),
        })
