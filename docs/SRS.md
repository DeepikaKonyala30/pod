# PodMind — Software Requirements Specification

**Version 1.0 | June 2025**
**AI-Driven Real-Time Pod Resource Discovery & Dependency Mapping System**
**Theme 2 — Containerized Systems Intelligence**

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Problem Statement & Domain Analysis](#2-problem-statement--domain-analysis)
3. [Proposed Solution](#3-proposed-solution)
4. [Technology Stack](#4-technology-stack)
5. [System Architecture](#5-system-architecture)
6. [Project Directory Structure](#6-project-directory-structure)
7. [Functional Requirements](#7-functional-requirements)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [API Specification](#9-api-specification)
10. [Dashboard Component Architecture](#10-dashboard-component-architecture)
11. [Demo Scenario](#11-demo-scenario)
12. [Risk Register](#12-risk-register)
13. [Future Enhancements](#13-future-enhancements)

---

## 1. Introduction

### 1.1 Purpose

This SRS defines the complete requirements, architecture, and implementation plan for **PodMind** — an AI-driven, real-time observability and intelligence platform for Kubernetes-based container environments.

### 1.2 Project Scope

PodMind targets **single-node Kubernetes deployments** (Minikube, K3s, MicroK8s) commonly used in edge, industrial, and academic environments. The system collects, correlates, and interprets real-time pod-level resource data across all namespaces, deploying a **multi-agent AI framework** to generate actionable intelligence — anomaly alerts, dependency graphs, forecasts, and natural-language recommendations.

### 1.3 Definitions & Acronyms

| Term | Definition |
|------|-----------|
| Pod | Smallest deployable unit in Kubernetes; encapsulates one or more containers |
| PVC | PersistentVolumeClaim — a request for storage by a pod |
| PromQL | Prometheus Query Language for time-series metric queries |
| LLM | Large Language Model — AI model for natural-language generation |
| Isolation Forest | Unsupervised ML algorithm for anomaly detection |
| Granger Causality | Statistical test to determine if one time series predicts another |
| WebSocket | Full-duplex communication protocol for real-time data push |
| MTTD | Mean Time to Detect |
| MTTR | Mean Time to Resolve |

---

## 2. Problem Statement & Domain Analysis

### 2.1 The Operational Gap

Modern container orchestration platforms enable rapid microservice deployment. Even single-node clusters routinely host hundreds of pods across multiple namespaces. Existing observability tools (Prometheus, Grafana, Datadog) collect raw metrics but:

- Present data as **isolated time-series streams**
- Do **not correlate** across resource types
- Do **not reason about causality**
- Do **not generate plain-language explanations**

### 2.2 Specific Challenges

| Challenge | Description |
|-----------|-------------|
| **Resource Attribution** | Attributing CPU/memory spikes to specific pods in shared-resource environments |
| **PVC I/O Correlation** | Linking PVC throughput saturation to cascading pod restarts |
| **Cross-Service Dependencies** | Understanding implicit resource dependencies between microservices |
| **Bursty Workloads** | ML training jobs and batch processors confuse threshold-based alerting |
| **Edge/Single-Node Gap** | No lightweight intelligent observability for edge clusters |

### 2.3 Stakeholder Impact Analysis

| Stakeholder | Current Pain | PodMind Impact |
|-------------|-------------|----------------|
| Platform Engineers | Manual log correlation | Automated root-cause analysis, 80% faster MTTR |
| System Operators | Alert fatigue | ML-based anomaly detection reduces false positives |
| DevOps / SRE Teams | No causal dependency maps | Live dependency graph surfaces hidden relationships |
| University / Research Labs | No lightweight K3s tool | Zero-overhead, single-node deployment |
| Industrial IoT Teams | Unmonitored edge clusters | Real-time NLP insights without cloud dependency |

### 2.4 Problem Quantification

- **MTTD** averages 18–34 minutes without intelligent correlation
- Engineers spend **40–60%** of incident response correlating metrics
- **23%** of pod restart cascades are PVC-related
- False positive rates of **35–55%** in clusters with 50+ pods

---

## 3. Proposed Solution

### 3.1 Core Principles

1. **Specialization** — Each AI agent is an expert in exactly one resource domain
2. **Correlation over Isolation** — All agent outputs feed an orchestration layer that reasons across resource types
3. **Actionable Language** — Every insight terminates in a concrete, human-readable recommendation

### 3.2 Five-Layer Architecture

| Layer | Purpose |
|-------|---------|
| **Data Layer** | Kubernetes cluster with demo stress workloads |
| **Collection Layer** | Prometheus, kube-state-metrics, custom Python collector, Loki |
| **Agent Layer** | Four specialized AI agents (CPU, Memory, Storage, Network) |
| **Intelligence Layer** | LLM orchestrator for synthesis, dependency graphs, forecasts |
| **Presentation Layer** | React dashboard with WebSocket, D3.js, Chart.js, NLP chat |

### 3.3 Key Differentiators

| Capability | Prometheus/Grafana | Datadog | PodMind |
|-----------|-------------------|---------|---------|
| Cross-resource correlation | Manual | Partial | **Automated (multi-agent)** |
| Causal dependency mapping | No | Limited | **Granger causality + ML** |
| LLM root-cause narrative | No | No | **Yes** |
| PVC I/O to pod restart linkage | No | No | **Yes** |
| NLP query interface | No | No | **Yes** |
| Works fully offline | Yes | No | **Yes (Ollama)** |

---

## 4. Technology Stack

### 4.1 Infrastructure Layer

| Component | Technology | Justification |
|-----------|-----------|---------------|
| Cluster runtime | Minikube 1.32 / K3s v1.29 | Lightweight single-node |
| Container runtime | containerd 1.7 | Default, minimal overhead |
| Metrics scraping | Prometheus 2.50 + kube-state-metrics 2.11 | Industry standard |
| Log aggregation | Loki 2.9 + Promtail | Lightweight, Prometheus ecosystem |
| Storage backend | Redis 7.2 (TimeSeries module) | Sub-millisecond reads |
| Message queue | Redis Streams | Low-latency agent event pipeline |

### 4.2 Data Collection Layer

| Component | Technology |
|-----------|-----------|
| Kubernetes API client | kubernetes-python SDK 28.1 |
| Prometheus client | prometheus-api-client 0.5 |
| Custom collector | Python 3.11 asyncio |
| PVC metrics | kubelet `/stats/summary` API |

### 4.3 Agent & Intelligence Layer

| Component | Technology |
|-----------|-----------|
| Agent orchestration | LangGraph 0.1 + custom Python |
| Anomaly detection | scikit-learn 1.4 (Isolation Forest, Z-score) |
| Dependency mapping | statsmodels (Granger causality) + NetworkX 3.2 |
| Forecasting | Facebook Prophet 1.1 / statsmodels ARIMA |
| LLM reasoning | Anthropic Claude / OpenAI GPT-4o / Ollama (llama3) |
| Correlation engine | NumPy + pandas + scipy |

### 4.4 Backend API Layer

| Component | Technology |
|-----------|-----------|
| Web framework | FastAPI 0.110 |
| WebSocket server | FastAPI + starlette WebSockets |
| Task scheduler | APScheduler 3.10 |
| API documentation | FastAPI `/docs` (Swagger UI) |

### 4.5 Frontend Dashboard

| Component | Technology |
|-----------|-----------|
| Framework | React 18 + Vite 5 |
| State management | Zustand 4 |
| Charts | Recharts 2.12 + Chart.js 4.4 |
| Dependency graph | D3.js 7 (force-directed layout) |
| UI components | shadcn/ui + Tailwind CSS 3 |

---

## 5. System Architecture

### 5.1 Data Flow Pipeline

```
[Kubernetes Cluster]
  | Kubernetes API + Prometheus scrape + kubelet /stats
  v
[Collection Service]  <-- Python asyncio collector
  | Redis TimeSeries (raw metrics, 5s resolution)
  v
[Multi-Agent Layer]   <-- CPU / Memory / Storage / Network agents
  | Redis Streams (agent event bus)
  v
[Orchestrator + LLM]  <-- Dependency mapper + LLM reasoning
  | FastAPI REST + WebSocket server
  v
[React Dashboard]     <-- Live charts, D3 graph, NLP chat
```

### 5.2 Data Collection Pipeline

#### Metric Collection Cadence

| Data Type | Source | Interval | Key Pattern |
|-----------|--------|----------|-------------|
| Pod CPU | `container_cpu_usage_seconds_total` | 5 sec | `cpu:{ns}:{pod}` |
| Pod Memory | `container_memory_*` | 5 sec | `mem:{ns}:{pod}` |
| PVC IOPS | kubelet `/stats/summary` | 10 sec | `pvc:{ns}:{pvc}` |
| Network rx/tx | `container_network_*` | 10 sec | `net:{ns}:{pod}` |
| Pod events | Kubernetes Events API | On event | `event:{ns}:{pod}:{ts}` |
| Pod metadata | kube-state-metrics | 30 sec | `meta:{ns}:{pod}` |
| Container logs | Kubernetes API pod/log | 60 sec | `log:{ns}:{pod}` |

#### Normalization Rules

- CPU → percentage of pod's requested CPU limit
- Memory → usage-to-limit ratio (RSS / limit)
- PVC throughput → normalized per GB of PVC capacity
- All series resampled to uniform 5-second interval with forward-fill

#### Redis TimeSeries Schema

```
TS.CREATE cpu:default:nginx-pod RETENTION 86400000 LABELS namespace default pod nginx-pod type cpu
TS.ADD cpu:default:nginx-pod * 0.342
TS.RANGE cpu:default:nginx-pod - + COUNT 360        # last 30 min at 5s
TS.RANGE cpu:default:nginx-pod - + AGGREGATION avg 60000   # 1-min averages
```

### 5.3 Multi-Agent Framework

#### Agent Execution Model

```python
async def run_analysis_cycle():
    metrics = await fetch_metric_windows(window_minutes=10)
    cpu_out, mem_out, stor_out, net_out = await asyncio.gather(
        cpu_agent.analyze(metrics),
        memory_agent.analyze(metrics),
        storage_agent.analyze(metrics),
        network_agent.analyze(metrics)
    )
    graph = dependency_mapper.build(cpu_out, mem_out, stor_out, net_out)
    insights = await orchestrator.synthesize(graph, [cpu_out, mem_out, stor_out, net_out])
    await redis.publish('insights', insights.to_json())
```

#### CPU Agent Logic
- Per-pod stats: mean, p95, p99, coefficient of variation (CV)
- **Isolation Forest** on CV values → bursty workloads
- **Z-score** on p99 → absolute CPU pressure
- Throttle detection: `throttled_seconds / total_seconds > 15%`
- CPU gradient via `numpy.gradient` → trending toward limits

#### Memory Agent Logic
- Memory utilization ratio (RSS / limit) per sample
- **Linear regression** over 10-min window → leak detection (slope > 0.5%/min)
- OOM risk: utilization > 85% in last sample
- Cache pressure: cache memory > 60% of RSS
- Correlate spikes with pod restart events

#### Storage Agent Logic
- Pod-to-PVC mapping matrix (handles ReadWriteMany)
- PVC saturation score: `current_IOPS / estimated_device_IOPS_limit`
- Time-shift correlation: PVC saturation before pod restart (2-min window)
- Sequential write detection: > 50 MB/s for > 30 consecutive seconds

#### Network/Log Agent Logic
- Network saturation: rx/tx > 80% of NIC capacity
- Chatty pods: > 10,000 packets/sec
- Log error rate: ERROR/WARN/FATAL lines per minute
- Connection pool exhaustion pattern matching

#### Dependency Mapper (Granger Causality)
- For every pod pair, test CPU/memory/network series
- **Granger causality** with max lag = 6 (30s), threshold p < 0.05
- Significant results → directed edges in NetworkX
- Optimization: limit to same-namespace pairs for >50 pods

### 5.4 LLM Orchestrator

#### Tiered Strategy

| Tier | Provider | Model | Latency |
|------|----------|-------|---------|
| 1 | Anthropic | claude-sonnet-4-20250514 | ~2–4s |
| 2 | OpenAI | gpt-4o-mini | ~1–3s |
| 3 | Ollama | llama3:8b / mistral:7b | ~5–15s |

#### LLM Output Schema

```json
{
  "root_causes": [{"rank": 1, "pod": "str", "namespace": "str", "resource": "str", "description": "str", "severity": "str", "confidence": 0.91}],
  "recommendations": [{"pod": "str", "action": "str", "priority": "str"}],
  "forecast_alerts": [{"pod": "str", "resource": "str", "eta_minutes": 47, "predicted_event": "str"}],
  "dependency_narrative": "str"
}
```

---

## 6. Project Directory Structure

```
podmind/
├── cluster/                          # Kubernetes manifests
│   ├── demo-workloads/
│   │   ├── cpu-stress.yaml
│   │   ├── memory-leak.yaml
│   │   ├── pvc-writer.yaml
│   │   └── network-flood.yaml
│   ├── prometheus/
│   │   ├── values.yaml
│   │   └── custom-rules.yaml
│   └── podmind/
│       ├── collector-deploy.yaml
│       ├── api-deploy.yaml
│       └── redis-deploy.yaml
├── collector/                        # Python data collection
│   ├── main.py
│   ├── k8s_client.py
│   ├── prometheus_client.py
│   ├── kubelet_client.py
│   ├── log_collector.py
│   ├── normalizer.py
│   └── redis_writer.py
├── agents/                           # Multi-agent AI framework
│   ├── orchestrator.py
│   ├── cpu_agent.py
│   ├── memory_agent.py
│   ├── storage_agent.py
│   ├── network_agent.py
│   ├── dependency_mapper.py
│   ├── forecaster.py
│   └── schemas.py
├── intelligence/                     # LLM reasoning layer
│   ├── llm_client.py
│   ├── prompt_templates.py
│   ├── recommendation_engine.py
│   └── insight_store.py
├── api/                              # FastAPI backend
│   ├── main.py
│   ├── routers/
│   │   ├── pods.py
│   │   ├── graph.py
│   │   ├── insights.py
│   │   ├── forecast.py
│   │   └── query.py
│   ├── websocket.py
│   └── models.py
├── dashboard/                        # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── PodGrid.jsx
│   │   │   ├── DependencyGraph.jsx
│   │   │   ├── AnomalyTimeline.jsx
│   │   │   ├── CorrelationHeatmap.jsx
│   │   │   ├── ForecastPanel.jsx
│   │   │   └── InsightChat.jsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.js
│   │   │   └── useNLPQuery.js
│   │   └── store/
│   │       ├── podStore.js
│   │       ├── graphStore.js
│   │       └── insightStore.js
│   └── vite.config.js
├── tests/
│   ├── test_cpu_agent.py
│   ├── test_dependency_mapper.py
│   ├── test_api_endpoints.py
│   └── fixtures/
├── docs/
│   ├── SRS.md
│   ├── architecture.md
│   └── demo-script.md
├── docker-compose.yml
├── Makefile
├── requirements.txt
└── README.md
```

---

## 7. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Discover all running pods across all namespaces every 30 seconds | Must Have |
| FR-02 | Collect CPU, memory, network, PVC metrics at 5-second resolution | Must Have |
| FR-03 | Detect CPU anomalies using Isolation Forest | Must Have |
| FR-04 | Detect memory leaks via linear regression on 10-min windows | Must Have |
| FR-05 | Correlate PVC I/O saturation with pod restart events (2-min lookback) | Must Have |
| FR-06 | Build causal dependency graph using Granger causality (p < 0.05) | Must Have |
| FR-07 | Generate NLP root-cause narratives via LLM each analysis cycle | Must Have |
| FR-08 | Forecast resource consumption for next 60 minutes per pod | Should Have |
| FR-09 | Expose REST API with all data as structured JSON | Must Have |
| FR-10 | Push live metrics via WebSocket at 5-second intervals | Must Have |
| FR-11 | Render force-directed dependency graph (D3.js) | Must Have |
| FR-12 | Provide chat-style NLP query interface | Must Have |
| FR-13 | Display anomaly timeline with pod-level event markers | Should Have |
| FR-14 | Display pod-to-pod correlation heatmap | Should Have |
| FR-15 | Support Ollama as offline LLM fallback | Should Have |

---

## 8. Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-01 | Performance | Full analysis cycle < 30 seconds on single node |
| NFR-02 | Performance | Dashboard renders within 500ms of WebSocket message |
| NFR-03 | Scalability | Handle up to 200 pods without degradation |
| NFR-04 | Reliability | Fallback to rule-based recommendations if LLM unavailable |
| NFR-05 | Reliability | Redis retains 24 hours of metric history |
| NFR-06 | Portability | Deploys on Minikube, K3s, and MicroK8s |
| NFR-07 | Usability | Key insights visible within 30 seconds of opening dashboard |
| NFR-08 | Security | No credentials stored outside Kubernetes Secrets |
| NFR-09 | Resource | PodMind < 500m CPU and < 512Mi memory when idle |

---

## 9. API Specification

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/pods` | List all pods with latest resource snapshot |
| `GET` | `/api/pods/{namespace}/{name}/metrics` | Time-series metrics for a specific pod |
| `GET` | `/api/graph` | Current dependency graph as JSON |
| `GET` | `/api/insights/latest` | Latest LLM-generated insight report |
| `GET` | `/api/anomalies` | Current anomaly list with severity |
| `GET` | `/api/forecast/{pod}` | Resource forecast for a pod (next 60 min) |
| `POST` | `/api/query` | NLP query → LLM answer |
| `WS` | `/ws/live` | WebSocket: metrics + insights every 5s |
| `GET` | `/api/pvcs` | PVC list with utilization and saturation |
| `GET` | `/health` | Component health status |

---

## 10. Dashboard Component Architecture

```
<App>
  <Sidebar>              # Namespace filter, pod search, settings
  <MainContent>
    <StatusBar>           # Cluster health, active anomaly count
    <PodGrid>             # Card per pod: sparklines, status badge
    <TabPanel>
      <DependencyGraph>   # D3.js force-directed, edge = causal strength
      <AnomalyTimeline>   # Chart.js swimlane, anomaly markers
      <CorrelationHeatmap># Pod x Pod Pearson r matrix
      <ForecastPanel>     # Prophet chart, horizon slider
      <InsightChat>       # Chat-style NLP query interface
    </TabPanel>
  </MainContent>
</App>
```

---

## 11. Demo Scenario

| Step | Action | Judges See |
|------|--------|------------|
| 1 | Deploy `memory-leak.yaml` | Pod appears in dashboard within 5s |
| 2 | Wait 3 minutes | Memory graph shows upward slope; agent flags it |
| 3 | LLM cycle triggers | "payments-sim is leaking at 2.1%/min. OOM in 41 min." |
| 4 | Deploy `pvc-writer.yaml` | Storage Agent detects I/O saturation |
| 5 | PVC writer causes restart | Dependency graph: pvc-writer → db-pod |
| 6 | Chat: "Why is db-pod restarting?" | "Correlates with pvc-writer saturating PVC at p=0.003" |

---

## 12. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM API unavailable during demo | Medium | High | Pre-cache responses; Ollama fallback |
| Granger produces no significant edges | Medium | Medium | Pre-recorded fixtures; replay mode |
| Minikube resource limits | Low | Medium | Allocate 4 CPU + 8GB RAM |
| Prometheus scrape gaps | Low | Medium | Forward-fill in normalizer |
| Dashboard perf with 100+ pods | Medium | Low | react-window; limit D3 to top 30 |
| Prophet too slow for 100+ pods | Medium | Low | Background thread; cached results |

---

## 13. Future Enhancements

### v1.1 (1–3 months)
- Multi-node cluster support
- Automated remediation via VPA/HPA
- Fine-tuned LLM for K8s SRE (LoRA)
- Slack / PagerDuty alert integration

### v2.0 (3–6 months)
- eBPF-based deep observability
- Cost attribution & optimization
- Chaos engineering integration
- GitOps-aware correlation

### v3.0 (6–12 months)
- Federated multi-cluster intelligence
- Digital twin simulation
- SLO-aware intelligence
- Natural language cluster configuration

---

*PodMind SRS v1.0 — Prepared for Hackathon Submission — June 2025*
