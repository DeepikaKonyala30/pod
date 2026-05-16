"""
PodMind — API Main Entrypoint

FastAPI application factory. Sets up CORS, registers routers,
initializes background scheduler, and manages WebSocket connections.

FIX: WebSocket endpoint path changed to /ws/live per SRS §9.
FIX: Added /api/anomalies endpoint registration.
FIX VULN-03: WebSocket handles PONG messages for heartbeat.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from config import settings
from api.redis_reader import RedisReader
from intelligence.insight_store import InsightStore
from api.websocket import ws_manager
from api.scheduler import AnalysisScheduler

# Routers
from api.routers import pods, graph, insights, forecast, query, pvcs, health, anomalies

logger = logging.getLogger("podmind.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup/shutdown of shared resources.
    """
    # 1. Initialize Redis clients
    redis_client = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    redis_reader = RedisReader(settings.redis_url)
    insight_store = InsightStore(redis_client)

    # Store in app state
    app.state.redis_client = redis_client
    app.state.redis_reader = redis_reader
    app.state.insight_store = insight_store

    # 2. Start background analysis scheduler
    scheduler = AnalysisScheduler(redis_reader, insight_store)
    app.state.scheduler = scheduler
    await scheduler.start()

    logger.info("API Application started.")
    yield

    # 3. Shutdown gracefully
    logger.info("Shutting down API...")
    await scheduler.stop()
    await redis_reader.close()
    await redis_client.aclose()


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="PodMind API",
    description="AI-Driven Real-Time Pod Resource Discovery & Dependency Mapping",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for React Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST Routers
app.include_router(health.router, tags=["Health"])
app.include_router(pods.router, prefix="/api", tags=["Pods"])
app.include_router(graph.router, prefix="/api", tags=["Graph"])
app.include_router(insights.router, prefix="/api", tags=["Insights"])
app.include_router(anomalies.router, prefix="/api", tags=["Anomalies"])
app.include_router(forecast.router, prefix="/api", tags=["Forecast"])
app.include_router(query.router, prefix="/api", tags=["Query"])
app.include_router(pvcs.router, prefix="/api", tags=["PVCs"])


# =============================================================================
# WebSocket Endpoint (SRS §9: /ws/live)
# =============================================================================

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    SRS §9 compliance: endpoint at /ws/live.
    VULN-03 FIX: Handles PONG messages for heartbeat protocol.
    """
    connected = await ws_manager.connect(websocket)
    if not connected:
        return  # Rejected at capacity

    try:
        while True:
            text = await websocket.receive_text()
            # VULN-03 FIX: Handle heartbeat PONG response
            try:
                msg = json.loads(text)
                if msg.get("type") == "PONG":
                    ws_manager.handle_pong(websocket)
            except (json.JSONDecodeError, AttributeError):
                pass  # Ignore malformed messages
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", str(e))
        ws_manager.disconnect(websocket)


# Backwards compatibility: also listen on /ws (redirect-style)
@app.websocket("/ws")
async def websocket_endpoint_compat(websocket: WebSocket):
    """Backwards-compatible WebSocket endpoint (redirects to /ws/live logic)."""
    await websocket_endpoint(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
