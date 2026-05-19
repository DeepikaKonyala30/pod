import { useEffect, useRef, useState, useCallback } from 'react';
import type { Insight, DependencyGraph, Pod, AgentActivity } from '../types';

interface WSMessage {
  type: string;
  data?: any;
  graph?: any;
  pods?: any[];
  agent_activity?: any;
  demo_mode?: boolean;
}

/**
 * WebSocket hook — auto-reconnect, heartbeat, handles all message types:
 *   NEW_INSIGHT  → insight + graph + agent_activity
 *   PODS_UPDATE  → live pod metrics (every 5s)
 *   PING         → heartbeat, responds with PONG
 */
export function useWebSocket(
  onNewInsight: (insight: Insight) => void,
  onNewGraph: (graph: DependencyGraph) => void,
  onPodsUpdate: (pods: Pod[]) => void,
  onAgentActivity: (activity: AgentActivity) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [lastMessageAt, setLastMessageAt] = useState<Date | null>(null);

  // Stable refs so we don't recreate the connection on every render
  const onInsightRef = useRef(onNewInsight);
  const onGraphRef = useRef(onNewGraph);
  const onPodsRef = useRef(onPodsUpdate);
  const onAgentRef = useRef(onAgentActivity);
  onInsightRef.current = onNewInsight;
  onGraphRef.current = onNewGraph;
  onPodsRef.current = onPodsUpdate;
  onAgentRef.current = onAgentActivity;

  const connect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* ignore */ }
    }

    const wsUrl = 'ws://localhost:8000/ws/live';
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      console.error('[WS] Failed to create WebSocket:', e);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      console.log('[WS] Connected to', wsUrl);
      setIsConnected(true);
      reconnectAttempt.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        setLastMessageAt(new Date());

        // Heartbeat
        if (msg.type === 'PING') {
          ws.send(JSON.stringify({ type: 'PONG' }));
          return;
        }

        // Full AI analysis result
        if (msg.type === 'NEW_INSIGHT') {
          if (msg.data)           onInsightRef.current(msg.data);
          if (msg.graph)          onGraphRef.current(msg.graph);
          if (msg.agent_activity) onAgentRef.current(msg.agent_activity);
        }

        // Fast pod metrics snapshot (every 5s)
        if (msg.type === 'PODS_UPDATE') {
          if (msg.pods?.length)   onPodsRef.current(msg.pods);
          if (msg.demo_mode !== undefined) setIsDemoMode(msg.demo_mode);
        }

      } catch (err) {
        console.error('[WS] Parse error:', err);
      }
    };

    ws.onclose = (event) => {
      console.log('[WS] Disconnected. Code:', event.code);
      setIsConnected(false);
      wsRef.current = null;
      if (event.code === 1000 && event.reason === 'Component unmounted') return;
      scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will handle reconnect
    };

    wsRef.current = ws;
  }, []);

  const scheduleReconnect = () => {
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt.current), 30000);
    reconnectAttempt.current++;
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempt.current})`);
    reconnectTimer.current = setTimeout(() => connect(), delay);
  };

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        try { wsRef.current.close(1000, 'Component unmounted'); } catch { /* ignore */ }
      }
    };
  }, [connect]);

  return { isConnected, isDemoMode, lastMessageAt };
}
