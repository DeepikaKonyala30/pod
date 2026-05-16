#!/usr/bin/env bash
# =============================================================================
# PodMind — Cluster Setup Script
# Standalone script to initialize Minikube + Prometheus + Redis for PodMind.
# Usage: bash cluster/setup.sh
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[PodMind]${NC} $1"; }
warn()  { echo -e "${YELLOW}[PodMind]${NC} $1"; }
error() { echo -e "${RED}[PodMind]${NC} $1"; exit 1; }

# ---- Step 1: Start Minikube ----
info "Starting Minikube cluster (4 CPU, 8GB RAM, 20GB disk)..."
minikube start \
    --cpus=4 \
    --memory=8192 \
    --disk-size=20g \
    --driver=docker \
    --addons=metrics-server,storage-provisioner,ingress

info "Minikube started successfully."
minikube status

# ---- Step 2: Create namespaces ----
info "Creating namespaces..."
kubectl create namespace podmind --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# ---- Step 3: Install Prometheus stack ----
info "Installing Prometheus stack via Helm..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update

helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
    -n monitoring \
    -f "$(dirname "$0")/prometheus/values.yaml" \
    --wait --timeout 5m

# Apply custom PodMind recording rules
kubectl apply -f "$(dirname "$0")/prometheus/custom-rules.yaml"
info "Prometheus stack deployed."

# ---- Step 4: Deploy Redis with TimeSeries ----
info "Deploying Redis with TimeSeries module..."
kubectl apply -f "$(dirname "$0")/podmind/redis-deploy.yaml"
kubectl wait --for=condition=ready pod -l app=podmind-redis -n podmind --timeout=120s
info "Redis deployed and ready."

# ---- Step 5: Verify ----
info "Verifying cluster components..."
echo ""
echo "  Namespaces:"
kubectl get namespaces | grep -E "podmind|monitoring"
echo ""
echo "  Prometheus pods:"
kubectl get pods -n monitoring --no-headers | head -5
echo ""
echo "  Redis pod:"
kubectl get pods -n podmind --no-headers
echo ""

info "============================================"
info "  Cluster setup complete!"
info "  Prometheus: kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090"
info "  Redis CLI:  kubectl exec -it -n podmind podmind-redis-0 -- redis-cli"
info "============================================"
