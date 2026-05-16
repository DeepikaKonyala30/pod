# PodMind — Demo Script

## Live Demo Guide (5 minutes)

### Pre-Demo Checklist
- [ ] Minikube running: `minikube status`
- [ ] Prometheus healthy: `kubectl get pods -n monitoring`
- [ ] PodMind services running: `kubectl get pods -n podmind`
- [ ] Dashboard open at `http://localhost:5173`
- [ ] API docs open at `http://localhost:8000/docs`

### Step 1 — Show Clean Cluster (30s)
1. Open dashboard — show empty PodGrid
2. Point out: "No anomalies detected" in StatusBar
3. Show the dependency graph — no edges

### Step 2 — Deploy Memory Leak (30s)
```bash
kubectl apply -f cluster/demo-workloads/memory-leak.yaml
```
- Watch PodGrid: new pod card appears within 5 seconds
- Narrate: "We're deploying a pod that leaks 10MB every 30 seconds"

### Step 3 — Wait for Detection (2 min)
- Memory sparkline shows steady upward slope
- Memory Agent flags it: amber → red status badge
- InsightChat populates with LLM narrative
- Point out: "payments-sim is leaking at 2.1%/min. OOM predicted in 41 minutes."

### Step 4 — Deploy PVC Writer (30s)
```bash
kubectl apply -f cluster/demo-workloads/pvc-writer.yaml
```
- Storage Agent detects I/O saturation on shared PVC
- Dependency graph shows new edge: `pvc-writer → db-victim`

### Step 5 — NLP Query (30s)
Type in InsightChat:
> "Why is db-victim-demo experiencing issues?"

Expected response:
> "db-victim-demo read latency correlates with pvc-writer-demo saturating
> the shared-data-pvc at 87% IOPS capacity (p=0.003, lag=18s)."

### Step 6 — Show Forecasting (30s)
- Click on memory-leak pod in PodGrid
- ForecastPanel shows Prophet prediction curve
- Point out OOM kill prediction timestamp

### Closing Statement
"PodMind doesn't just monitor — it understands. It identifies root causes,
maps hidden dependencies, and tells you exactly what to fix, in plain English."
