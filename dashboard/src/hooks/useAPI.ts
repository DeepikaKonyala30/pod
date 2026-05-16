import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import type { Insight, DependencyGraph, SystemHealth } from '../types';

const API_BASE = 'http://localhost:8000/api';

export function useAPI() {
  const [insight, setInsight] = useState<Insight | null>(null);
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchInitialData = useCallback(async () => {
    setLoading(true);
    try {
      const [insightRes, graphRes, healthRes] = await Promise.all([
        axios.get(`${API_BASE}/insights/latest`).catch(() => ({ data: { data: null } })),
        axios.get(`${API_BASE}/graph`).catch(() => ({ data: { data: null } })),
        axios.get('http://localhost:8000/health').catch(() => ({ data: null }))
      ]);

      if (insightRes.data?.data) setInsight(insightRes.data.data);
      if (graphRes.data?.data) setGraph(graphRes.data.data);
      if (healthRes.data) setHealth(healthRes.data);
    } catch (err) {
      console.error("Failed to fetch initial data", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  const queryNLP = async (query: string) => {
    try {
      const res = await axios.post(`${API_BASE}/query`, { query });
      return res.data.data.answer;
    } catch (err) {
      console.error(err);
      return "Sorry, I couldn't process your request at this time.";
    }
  };

  return { insight, graph, health, loading, queryNLP, setInsight, setGraph };
}
