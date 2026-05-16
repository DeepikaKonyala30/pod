"""
PodMind — WebSocket Manager

Manages real-time WebSocket connections to broadcast cluster metrics,
analysis insights, and forecast alerts to the React dashboard.

VULN-03 FIX: Implements heartbeat ping/pong, connection TTL,
max-connection limits, and dead connection cleanup to prevent
state exhaustion (DoS) attacks.
"""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("podmind.api.websocket")

# Security limits (VULN-03 FIX)
MAX_CONNECTIONS = 100
HEARTBEAT_INTERVAL_SEC = 30
CONNECTION_TTL_SEC = 3600  # 1 hour max connection lifetime


class _ConnectionEntry:
    """Tracks metadata for a single WebSocket connection."""

    __slots__ = ("ws", "connected_at", "last_pong", "_heartbeat_task")

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.connected_at = time.monotonic()
        self.last_pong = time.monotonic()
        self._heartbeat_task: asyncio.Task | None = None


class ConnectionManager:
    """
    Manages active WebSocket connections with security protections.

    VULN-03 FIX:
    - Max connection limit (default: 100)
    - Heartbeat ping every 30s — drops dead connections
    - Connection TTL (default: 1 hour) — auto-disconnect stale clients
    - Thread-safe connection tracking
    """

    def __init__(
        self,
        max_connections: int = MAX_CONNECTIONS,
        heartbeat_interval: int = HEARTBEAT_INTERVAL_SEC,
        connection_ttl: int = CONNECTION_TTL_SEC,
    ):
        self._connections: dict[WebSocket, _ConnectionEntry] = {}
        self._max_connections = max_connections
        self._heartbeat_interval = heartbeat_interval
        self._connection_ttl = connection_ttl

    @property
    def active_connections(self) -> list[WebSocket]:
        """List of active WebSocket connections (backwards compat)."""
        return list(self._connections.keys())

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> bool:
        """
        Accept a new WebSocket connection with capacity check.

        Returns False if at capacity (VULN-03 protection).
        """
        # VULN-03 FIX: Reject if at capacity
        if len(self._connections) >= self._max_connections:
            logger.warning(
                "WebSocket connection rejected: at capacity (%d/%d)",
                len(self._connections), self._max_connections,
            )
            await websocket.close(code=1013, reason="Server at capacity")
            return False

        await websocket.accept()
        entry = _ConnectionEntry(websocket)

        # Start heartbeat task
        entry._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(websocket)
        )

        self._connections[websocket] = entry
        logger.info(
            "New WebSocket connection. Total: %d/%d",
            len(self._connections), self._max_connections,
        )
        return True

    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket and cancel its heartbeat."""
        entry = self._connections.pop(websocket, None)
        if entry and entry._heartbeat_task:
            entry._heartbeat_task.cancel()
        logger.info(
            "WebSocket disconnected. Total: %d/%d",
            len(self._connections), self._max_connections,
        )

    def handle_pong(self, websocket: WebSocket):
        """Update last_pong timestamp when client responds to heartbeat."""
        entry = self._connections.get(websocket)
        if entry:
            entry.last_pong = time.monotonic()

    async def broadcast(self, message: dict[str, Any]):
        """Broadcast a JSON message to all connected clients."""
        if not self._connections:
            return

        json_msg = json.dumps(message)
        dead_connections = []

        for ws, entry in list(self._connections.items()):
            # VULN-03 FIX: Check TTL before sending
            if time.monotonic() - entry.connected_at > self._connection_ttl:
                logger.info("Connection TTL expired, disconnecting")
                dead_connections.append(ws)
                continue

            try:
                await ws.send_text(json_msg)
            except Exception as e:
                logger.debug("Failed to send WS message, removing client: %s", str(e))
                dead_connections.append(ws)

        # Cleanup dead connections
        for dead in dead_connections:
            try:
                await dead.close(code=1000, reason="TTL expired or send failed")
            except Exception:
                pass
            self.disconnect(dead)

    async def _heartbeat_loop(self, websocket: WebSocket):
        """
        VULN-03 FIX: Send periodic heartbeat pings to detect dead connections.

        If a client doesn't respond with a PONG within 2 heartbeat intervals,
        the connection is considered dead and removed.
        """
        try:
            while websocket in self._connections:
                await asyncio.sleep(self._heartbeat_interval)

                entry = self._connections.get(websocket)
                if not entry:
                    break

                # Check if client has responded recently
                time_since_pong = time.monotonic() - entry.last_pong
                if time_since_pong > self._heartbeat_interval * 2:
                    logger.info("Client unresponsive (%.1fs), disconnecting", time_since_pong)
                    try:
                        await websocket.close(code=1000, reason="Heartbeat timeout")
                    except Exception:
                        pass
                    self.disconnect(websocket)
                    break

                # Send heartbeat ping
                try:
                    await websocket.send_text('{"type":"PING"}')
                except Exception:
                    self.disconnect(websocket)
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Heartbeat loop error: %s", str(e))
            self.disconnect(websocket)


# Global singleton manager
ws_manager = ConnectionManager()
