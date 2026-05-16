"""
PodMind — Insight Store

Redis-backed persistence layer for LLM-generated insights.
Stores insight history with TTL, supports querying by time range,
and provides the latest insight for dashboard display.

Storage schema:
  - insight:latest     → JSON of most recent InsightOutput (Hash)
  - insight:history    → Sorted set of insight IDs by timestamp
  - insight:{id}       → JSON of a specific InsightOutput (String with TTL)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from agents.schemas import InsightOutput

logger = logging.getLogger("podmind.intelligence.insight_store")


class InsightStore:
    """
    Persists and retrieves LLM-generated insights in Redis.

    Maintains:
      - The latest insight for real-time dashboard display
      - A capped history of recent insights for trend analysis
      - TTL-based automatic cleanup of old insights
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        max_history: int = 100,
        insight_ttl_hours: int = 24,
    ):
        """
        Args:
            redis_client: Async Redis client instance.
            max_history: Maximum number of insights to retain.
            insight_ttl_hours: TTL for individual insight records.
        """
        self._redis = redis_client
        self._max_history = max_history
        self._ttl_seconds = insight_ttl_hours * 3600

    # -------------------------------------------------------------------------
    # Write Operations
    # -------------------------------------------------------------------------

    async def store_insight(self, insight: InsightOutput) -> str:
        """
        Store a new insight, update 'latest', and trim history.

        Args:
            insight: The InsightOutput to persist.

        Returns:
            Generated insight ID.
        """
        insight_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc)
        ts_unix = timestamp.timestamp()

        # Serialize to JSON
        insight_json = insight.model_dump_json()

        pipe = self._redis.pipeline()

        # Store individual insight with TTL
        insight_key = f"insight:{insight_id}"
        pipe.set(insight_key, insight_json, ex=self._ttl_seconds)

        # Update latest pointer
        pipe.hset("insight:latest", mapping={
            "id": insight_id,
            "data": insight_json,
            "timestamp": timestamp.isoformat(),
            "summary": insight.summary or "",
            "root_cause_count": str(len(insight.root_causes)),
            "recommendation_count": str(len(insight.recommendations)),
            "forecast_alert_count": str(len(insight.forecast_alerts)),
        })

        # Add to sorted history (score = timestamp)
        pipe.zadd("insight:history", {insight_id: ts_unix})

        # Trim history to max_history
        pipe.zremrangebyrank("insight:history", 0, -(self._max_history + 1))

        await pipe.execute()

        logger.info(
            "Stored insight %s: %d root causes, %d recommendations, %d alerts",
            insight_id,
            len(insight.root_causes),
            len(insight.recommendations),
            len(insight.forecast_alerts),
        )

        return insight_id

    # -------------------------------------------------------------------------
    # Read Operations
    # -------------------------------------------------------------------------

    async def get_latest(self) -> Optional[InsightOutput]:
        """
        Get the most recent insight.

        Returns:
            InsightOutput or None if no insights exist.
        """
        data = await self._redis.hget("insight:latest", "data")
        if not data:
            return None

        try:
            return InsightOutput.model_validate_json(data)
        except Exception as e:
            logger.warning("Failed to parse latest insight: %s", str(e))
            return None

    async def get_latest_metadata(self) -> Optional[dict]:
        """Get metadata about the latest insight (without full data)."""
        data = await self._redis.hgetall("insight:latest")
        if not data:
            return None

        return {
            "id": data.get("id", ""),
            "timestamp": data.get("timestamp", ""),
            "summary": data.get("summary", ""),
            "root_cause_count": int(data.get("root_cause_count", 0)),
            "recommendation_count": int(data.get("recommendation_count", 0)),
            "forecast_alert_count": int(data.get("forecast_alert_count", 0)),
        }

    async def get_by_id(self, insight_id: str) -> Optional[InsightOutput]:
        """
        Retrieve a specific insight by ID.

        Args:
            insight_id: The insight's unique identifier.

        Returns:
            InsightOutput or None if not found or expired.
        """
        data = await self._redis.get(f"insight:{insight_id}")
        if not data:
            return None

        try:
            return InsightOutput.model_validate_json(data)
        except Exception as e:
            logger.warning("Failed to parse insight %s: %s", insight_id, str(e))
            return None

    async def get_history(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """
        Get recent insight IDs with timestamps.

        Args:
            limit: Maximum number of results.
            offset: Number of entries to skip (newest first).

        Returns:
            List of {"id": str, "timestamp": float} dicts, newest first.
        """
        # Get from sorted set (newest first)
        results = await self._redis.zrevrange(
            "insight:history",
            offset,
            offset + limit - 1,
            withscores=True,
        )

        history = []
        for insight_id, score in results:
            ts = datetime.fromtimestamp(score, tz=timezone.utc)
            history.append({
                "id": insight_id,
                "timestamp": ts.isoformat(),
                "timestamp_unix": score,
            })

        return history

    async def get_history_with_summaries(self, limit: int = 10) -> list[dict]:
        """
        Get recent insights with their summaries (for dashboard list view).
        Fetches full insight data for each history entry.
        """
        history = await self.get_history(limit=limit)

        results = []
        for entry in history:
            insight = await self.get_by_id(entry["id"])
            if insight:
                results.append({
                    "id": entry["id"],
                    "timestamp": entry["timestamp"],
                    "summary": insight.summary,
                    "root_cause_count": len(insight.root_causes),
                    "recommendation_count": len(insight.recommendations),
                    "top_severity": (
                        insight.root_causes[0].severity.value
                        if insight.root_causes else "info"
                    ),
                })

        return results

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    async def clear_all(self) -> int:
        """Delete all insight data. Used for testing."""
        history = await self._redis.zrange("insight:history", 0, -1)

        pipe = self._redis.pipeline()
        for insight_id in history:
            pipe.delete(f"insight:{insight_id}")
        pipe.delete("insight:latest")
        pipe.delete("insight:history")

        results = await pipe.execute()
        count = sum(1 for r in results if r)
        logger.info("Cleared %d insight records", count)
        return count

    async def count(self) -> int:
        """Get the number of insights in history."""
        return await self._redis.zcard("insight:history")
