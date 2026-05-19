import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import type { Insight, DependencyGraph, SystemHealth, Pod, AgentActivity } from '../types';

const API_BASE = 'http://localhost:8000/api';
const HEALTH_BASE = 'http://localhost:8000';

export function useAPI() {
  const [insight, setInsight] = useState<Insight | null>(null);
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [pods, setPods] = useState<Pod[]>([]);
  const [agentActivity, setAgentActivity] = useState<AgentActivity | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // ── Initial data fetch ──────────────────────────────────────────────────
  const fetchInitialData = useCallback(async () => {
    setLoading(true);
    try {
      const [insightRes, graphRes, healthRes, podsRes] = await Promise.allSettled([
        axios.get(`${API_BASE}/insights/latest`, { timeout: 5000 }),
        axios.get(`${API_BASE}/graph`,            { timeout: 5000 }),
        axios.get(`${HEALTH_BASE}/health`,         { timeout: 5000 }),
        axios.get(`${API_BASE}/pods`,             { timeout: 5000 }),
      ]);

      if (insightRes.status === 'fulfilled' && insightRes.value.data?.data) {
        setInsight(insightRes.value.data.data);
      }
      if (graphRes.status === 'fulfilled' && graphRes.value.data?.data) {
        setGraph(graphRes.value.data.data);
      }
      if (healthRes.status === 'fulfilled' && healthRes.value.data) {
        setHealth(healthRes.value.data);
      }
      if (podsRes.status === 'fulfilled' && podsRes.value.data?.data) {
        setPods(podsRes.value.data.data);
      }

      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to fetch initial data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Polling — pods every 5s, insight every 15s ──────────────────────────
  const pollPods = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/pods`, { timeout: 4000 });
      if (res.data?.data?.length) {
        setPods(res.data.data);
        setLastUpdated(new Date());
      }
    } catch { /* keep stale data */ }
  }, []);

  const pollInsight = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/insights/latest`, { timeout: 4000 });
      if (res.data?.data) {
        setInsight(res.data.data);
        setLastUpdated(new Date());
      }
    } catch { /* keep stale data */ }
  }, []);

  useEffect(() => {
    fetchInitialData();

    // Poll pods every 5s
    const podTimer = setInterval(pollPods, 5000);
    // Poll insight every 15s as backup to WebSocket
    const insightTimer = setInterval(pollInsight, 15000);

    return () => {
      clearInterval(podTimer);
      clearInterval(insightTimer);
    };
  }, [fetchInitialData, pollPods, pollInsight]);

  // ── NLP Query with timeout ───────────────────────────────────────────────
  const queryNLP = async (query: string): Promise<string> => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const res = await axios.post(
        `${API_BASE}/query`,
        { query },
        { signal: controller.signal, timeout: 30000 }
      );
      clearTimeout(timeoutId);
      return res.data?.data?.answer ?? "Sorry, I couldn't retrieve an answer right now.";
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError' || err.code === 'ECONNABORTED') {
        return "Request timed out. The AI is processing a complex query — please try again.";
      }
      console.error('NLP query error:', err);
      return "Sorry, I couldn't process your request. Please check your connection and try again.";
    }
  };

  return {
    insight, setInsight,
    graph, setGraph,
    health,
    pods, setPods,
    agentActivity, setAgentActivity,
    loading,
    lastUpdated,
    queryNLP,
  };
}
