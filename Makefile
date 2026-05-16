# =============================================================================
# PodMind — Makefile
# One-command targets for setup, development, testing, and demo.
# =============================================================================
# Usage:
#   make setup       — Full cluster + dependency installation
#   make dev         — Start local dev (Redis + API + dashboard)
#   make demo        — Full demo: cluster + workloads + services
#   make test        — Run all tests
#   make clean       — Tear down everything
# =============================================================================

.PHONY: help setup setup-cluster setup-prometheus setup-redis setup-deps \
        dev dev-redis dev-api dev-dashboard dev-collector \
        demo demo-workloads demo-clean \
        test test-agents test-api test-coverage \
        clean clean-cluster clean-docker logs redis-cli

# Default target
help: ## Show this help message
	@echo "==============================================="
	@echo "  PodMind — Development Commands"
	@echo "==============================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# SETUP
# =============================================================================

setup: setup-deps setup-cluster setup-prometheus setup-redis ## Full setup: deps + cluster + Prometheus + Redis
	@echo "[PodMind] Setup complete. Run 'make dev' to start development."

setup-deps: ## Install Python and Node dependencies
	pip install -r requirements.txt
	cd dashboard && npm install

setup-cluster: ## Start Minikube with required addons
	minikube start --cpus=4 --memory=8192 --disk-size=20g --driver=docker
	minikube addons enable metrics-server
	minikube addons enable storage-provisioner
	minikube addons enable ingress
	kubectl create namespace podmind --dry-run=client -o yaml | kubectl apply -f -
	kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
	@echo "[PodMind] Cluster ready."

setup-prometheus: ## Install Prometheus stack via Helm
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	helm install prometheus prometheus-community/kube-prometheus-stack \
		-n monitoring \
		-f cluster/prometheus/values.yaml \
		--wait --timeout 5m
	kubectl apply -f cluster/prometheus/custom-rules.yaml
	@echo "[PodMind] Prometheus stack deployed."

setup-redis: ## Deploy Redis with TimeSeries module to cluster
	kubectl apply -f cluster/podmind/redis-deploy.yaml
	kubectl wait --for=condition=ready pod -l app=podmind-redis -n podmind --timeout=120s
	@echo "[PodMind] Redis deployed and ready."

# =============================================================================
# LOCAL DEVELOPMENT
# =============================================================================

dev: dev-redis ## Start local development environment
	@echo "[PodMind] Redis running. Start services with:"
	@echo "  Terminal 1: make dev-collector"
	@echo "  Terminal 2: make dev-api"
	@echo "  Terminal 3: make dev-dashboard"

dev-redis: ## Start Redis via docker-compose (local)
	docker-compose up -d redis
	@echo "[PodMind] Redis available at localhost:6379"

dev-collector: ## Start the collector service locally
	cd collector && python main.py

dev-api: ## Start the FastAPI server locally
	cd api && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

dev-dashboard: ## Start the React dashboard locally
	cd dashboard && npm run dev

# =============================================================================
# DEMO
# =============================================================================

demo: setup demo-workloads ## Full demo: setup cluster + deploy workloads + start services
	@echo "==============================================="
	@echo "  PodMind Demo Ready!"
	@echo "  Dashboard: http://localhost:5173"
	@echo "  API Docs:  http://localhost:8000/docs"
	@echo "  Redis:     localhost:6379"
	@echo "==============================================="

demo-workloads: ## Deploy demo stress workloads to cluster
	kubectl apply -f cluster/demo-workloads/cpu-stress.yaml
	kubectl apply -f cluster/demo-workloads/memory-leak.yaml
	kubectl apply -f cluster/demo-workloads/pvc-writer.yaml
	kubectl apply -f cluster/demo-workloads/network-flood.yaml
	@echo "[PodMind] Demo workloads deployed. Wait ~30s for metrics."

demo-clean: ## Remove demo stress workloads
	kubectl delete -f cluster/demo-workloads/ --ignore-not-found=true
	@echo "[PodMind] Demo workloads removed."

# =============================================================================
# TESTING
# =============================================================================

test: ## Run all tests
	pytest tests/ -v --tb=short

test-agents: ## Run agent tests only
	pytest tests/test_cpu_agent.py tests/test_dependency_mapper.py -v

test-api: ## Run API endpoint tests only
	pytest tests/test_api_endpoints.py -v

test-coverage: ## Run tests with coverage report
	pytest tests/ --cov=collector --cov=agents --cov=intelligence --cov=api \
		--cov-report=term-missing --cov-report=html

# =============================================================================
# UTILITIES
# =============================================================================

logs: ## Tail PodMind pod logs (cluster mode)
	kubectl logs -f -l app.kubernetes.io/part-of=podmind -n podmind --all-containers --max-log-requests=10

redis-cli: ## Open Redis CLI (local)
	docker exec -it podmind-redis redis-cli

lint: ## Run linting
	ruff check collector/ agents/ intelligence/ api/
	ruff format --check collector/ agents/ intelligence/ api/

format: ## Format code
	ruff format collector/ agents/ intelligence/ api/

# =============================================================================
# CLEANUP
# =============================================================================

clean: clean-docker ## Full cleanup
	@echo "[PodMind] Cleanup complete."

clean-cluster: ## Delete Minikube cluster
	minikube delete
	@echo "[PodMind] Cluster deleted."

clean-docker: ## Stop and remove docker-compose services
	docker-compose down -v
	@echo "[PodMind] Docker services removed."
