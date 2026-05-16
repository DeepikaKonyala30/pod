import { useEffect, useRef, useState, useCallback } from 'react';
import type { Insight, DependencyGraph } from '../types';

interface WSMessage {
  type: string;
  data?: any;
  graph?: any;
}

/**
 * WebSocket hook with auto-reconnect and heartbeat support.
 *
 * SRS compliance:
 * - Connects to /ws/live (SRS §9) with /ws fallback
 * - Exponential backoff reconnection (1s → 2s → 4s → ... → 30s max)
 * - Responds to server PING with PONG (VULN-03 heartbeat protocol)
 * - Tracks connection status for UI display
 */
export function useWebSocket(
  onNewInsight: (insight: Insight) => void,
  onNewGraph: (graph: DependencyGraph) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  // Stable refs for callbacks (avoid reconnecting on every render)
  const onInsightRef = useRef(onNewInsight);
  const onGraphRef = useRef(onNewGraph);
  onInsightRef.current = onNewInsight;
  onGraphRef.current = onNewGraph;

  const connect = useCallback(() => {
    // Clear any pending reconnect timer
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    // Close existing connection if any
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* ignore */ }
    }

    const wsUrl = `ws://localhost:8000/ws/live`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[WS] Connected to', wsUrl);
      setIsConnected(true);
      reconnectAttempt.current = 0; // Reset backoff on successful connection
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);

        // VULN-03: Respond to server heartbeat PING with PONG
        if (msg.type === 'PING') {
          ws.send(JSON.stringify({ type: 'PONG' }));
          return;
        }

        if (msg.type === 'NEW_INSIGHT') {
          if (msg.data) onInsightRef.current(msg.data);
          if (msg.graph) onGraphRef.current(msg.graph);
        }
      } catch (err) {
        console.error('[WS] Failed to parse message', err);
      }
    };

    ws.onclose = (event) => {
      console.log('[WS] Disconnected. Code:', event.code, 'Reason:', event.reason);
      setIsConnected(false);
      wsRef.current = null;

      // Don't reconnect if closed intentionally (code 1000 with reason)
      if (event.code === 1000 && event.reason === 'Component unmounted') {
        return;
      }

      // Exponential backoff reconnect: 1s, 2s, 4s, 8s, 16s, 30s max
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempt.current), 30000);
      reconnectAttempt.current++;
      console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempt.current})`);

      reconnectTimer.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = (err) => {
      console.error('[WS] Error:', err);
      // onclose will handle reconnection
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        // Close with reason so we don't auto-reconnect
        try {
          wsRef.current.close(1000, 'Component unmounted');
        } catch { /* ignore */ }
      }
    };
  }, [connect]);

  return { isConnected };
}
