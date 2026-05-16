# PodMind — Architecture Documentation

## System Overview

PodMind follows a **five-layer pipeline architecture** with unidirectional data flow
from the Kubernetes cluster upward through collection, analysis, intelligence, and
presentation. A bidirectional path between the API and intelligence layers supports
on-demand NLP queries from the dashboard.

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 5: PRESENTATION                                                      │
│  React 18 + Vite 5 | D3.js | Chart.js | Zustand | WebSocket client         │
│  ┌──────────┐ ┌──────────────┐ ┌────────────┐ ┌─────────────┐ ┌─────────┐  │
│  │ PodGrid  │ │ DepGraph(D3) │ │ Timeline   │ │ Heatmap     │ │ NLPChat │  │
│  └──────────┘ └──────────────┘ └────────────┘ └─────────────┘ └─────────┘  │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ WebSocket + REST
┌───────────────────────────────────▼──────────────────────────────────────────┐
│  LAYER 4: API GATEWAY                                                        │
│  FastAPI 0.110 | WebSocket Manager | APScheduler                             │
│  /api/pods | /api/graph | /api/insights | /api/query | /ws/live              │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼──────────────────────────────────────────┐
│  LAYER 3: INTELLIGENCE                                                       │
│  LLM Orchestrator (Claude/GPT/Ollama) | Prompt Templates | Recommendation   │
│  ┌──────────────────────────────────────────────────────────────────────┐     │
│  │  MULTI-AGENT FRAMEWORK (LangGraph)                                   │     │
│  │  ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                  │     │
│  │  │CPU Agt │ │Memory Agt│ │Stor. Agt │ │Net. Agt  │  ← parallel     │     │
│  │  └────┬───┘ └────┬─────┘ └────┬─────┘ └────┬─────┘                  │     │
│  │       └──────────┬┴───────────┬┘            │                        │     │
│  │                  ▼            ▼              │                        │     │
│  │          Dependency Mapper (Granger)    Forecaster (Prophet)          │     │
│  └──────────────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ Redis Streams (event bus)
┌───────────────────────────────────▼──────────────────────────────────────────┐
│  LAYER 2: DATA COLLECTION                                                    │
│  Python asyncio Collector | APScheduler (5s/10s/30s/60s jobs)                │
│  ┌──────────────┐ ┌────────────────┐ ┌──────────────┐ ┌───────────────┐     │
│  │ K8s Client   │ │ Prom Client    │ │ Kubelet      │ │ Log Collector │     │
│  │ (pods,PVCs)  │ │ (PromQL→DF)    │ │ (/stats/sum) │ │ (pod logs)    │     │
│  └──────┬───────┘ └──────┬─────────┘ └──────┬───────┘ └──────┬────────┘     │
│         └───────────────┬┴──────────────────┬┘               │              │
│                         ▼                                     │              │
│                   Normalizer (CPU→%, Mem→ratio, 5s resample)  │              │
│                         ▼                                     │              │
│                   Redis Writer (TS.ADD + XADD)                │              │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ K8s API + Prometheus scrape
┌───────────────────────────────────▼──────────────────────────────────────────┐
│  LAYER 1: INFRASTRUCTURE                                                     │
│  Minikube/K3s/MicroK8s | Prometheus 2.50 | kube-state-metrics               │
│  Redis 7.2 (TimeSeries) | containerd 1.7                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │  Kubernetes Cluster (Single Node)                                    │     │
│  │  [pods] [PVCs] [services] [events] [node metrics] [container logs]  │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Collection** (every 5–60s): Metrics scraped from Prometheus, kubelet, K8s API
2. **Normalization**: CPU→%, Memory→ratio, PVC→per-GB; resampled to 5s uniform
3. **Storage**: Redis TimeSeries with 24h retention; Redis Streams for events
4. **Analysis** (every 30s): 4 agents run in parallel via LangGraph
5. **Correlation**: Granger causality builds directed dependency graph
6. **Synthesis**: LLM generates root-cause narrative + recommendations
7. **Delivery**: FastAPI REST + WebSocket pushes to React dashboard

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Redis TimeSeries over InfluxDB | Sub-ms reads; native TS commands; single Redis for cache + TS + streams |
| Parallel agents via asyncio.gather | Each agent is independent; 4x speedup over sequential |
| Granger causality over Pearson | Detects directional causation, not just correlation |
| Tiered LLM with local fallback | Works in air-gapped environments; no cloud dependency |
| Pydantic schemas for all boundaries | Runtime validation at every agent output and API response |
| WebSocket over SSE | Full-duplex needed for NLP query responses |
