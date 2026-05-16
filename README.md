# PodMind 🧠

> **AI-Driven Real-Time Pod Resource Discovery & Dependency Mapping**
> An intelligent observability platform for Kubernetes that goes beyond monitoring — it *understands* your cluster.

![PodMind Status](https://img.shields.io/badge/Status-Production_Ready-success?style=for-the-badge)
![Python Version](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi)

---

## 📖 Table of Contents

1. [What is PodMind?](#-what-is-podmind)
2. [Key Features](#-key-features)
3. [Architecture Overview](#-architecture-overview)
4. [Prerequisites](#-prerequisites)
5. [Step-by-Step Installation](#-step-by-step-installation)
   - [Windows Users](#for-windows-users)
   - [Mac/Linux Users](#for-maclinux-users)
6. [Navigating the Dashboard](#-navigating-the-dashboard)
7. [Running the Test Suite](#-running-the-test-suite)
8. [API Documentation](#-api-documentation)

---

## 🔍 What is PodMind?

When a Kubernetes cluster breaks, standard monitoring tools tell you *what* failed (e.g., "Memory at 100%"). **PodMind tells you *why* it failed.**

PodMind is a cutting-edge multi-agent AI system. It collects real-time pod-level resource metrics (CPU, memory, storage, network), correlates them, and uses an advanced **Large Language Model (LLM)** orchestrator to generate human-readable root-cause analyses, natural language insights, and predictive forecasts.

---

## ✨ Key Features

- **Multi-Agent Anomaly Detection:** Four specialized AI agents continuously monitor CPU, Memory, Storage, and Network, using Isolation Forests to detect subtle anomalies before they cause outages.
- **Causal Dependency Mapping:** Uses Granger causality to discover hidden pod-to-pod relationships (e.g., *Pod A's network flood is causing Pod B's I/O starvation*).
- **Predictive Forecasting:** Prophet-based time-series forecasting predicts impending Resource Exhaustion (e.g., predicting an OOM Kill 40 minutes in advance).
- **LLM Root-Cause Analysis:** Translates complex mathematical anomalies into plain English explanations and actionable recommendations.
- **NLP "Ask Your Cluster" Chat:** A chat interface where you can ask questions like *"Why did the payment-pod restart?"* and get detailed answers instantly.
- **Real-Time Interactive Dashboard:** A stunning, dark-mode React UI with live WebSocket updates, D3.js dependency graphs, and anomaly swimlane timelines.

---

## 🏗 Architecture Overview

PodMind operates through a streamlined, highly asynchronous data pipeline:

```text
[Kubernetes / Hosts]  →  [Metrics Collector]  →  [Redis TimeSeries]
                                                         ↓
                                              [Multi-Agent Pipeline]
                                         (CPU, Memory, Storage, Network)
                                                         ↓
                                               [LLM Orchestrator]
                                            (Claude / GPT-4o / Ollama)
                                                         ↓
                                              [FastAPI + WebSockets]
                                                         ↓
                                               [React Dashboard UI]
```

---

## ⚙️ Prerequisites

Before you begin, ensure your local environment meets the following requirements:

- **Docker Desktop** (Must be running for the Redis database)
- **Python 3.11 or higher**
- **Node.js 18 or higher** (with `npm`)
- **Git**

---

## 🚀 Step-by-Step Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/podmind.git
cd podmind
```

### 2. Configure Environment Variables
Copy the `.env.example` file to `.env`:
```bash
cp .env.example .env
```
Open the `.env` file and insert your API keys for the LLM you wish to use (e.g., `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`).

---

### For Windows Users

We've provided a fully automated startup script for Windows. Make sure **Docker Desktop** is open and running, then simply execute:

```powershell
# Open a fresh PowerShell terminal in the project folder
.\start-windows.ps1
```

**What the script does automatically:**
1. Starts the Redis database via Docker Compose.
2. Creates a Python virtual environment and installs backend dependencies.
3. Opens a new PowerShell window running the FastAPI backend.
4. Installs Node modules and starts the React dashboard in your current terminal.

---

### For Mac/Linux Users

**1. Start the Redis Database**
```bash
docker-compose up -d redis
```

**2. Setup and Start the Backend**
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

**3. Setup and Start the Frontend**
Open a new terminal tab:
```bash
cd dashboard
npm install
npm run dev
```

---

## 🖥 Navigating the Dashboard

Once the app is running, open your browser to **http://localhost:5173**.

The PodMind dashboard consists of four main sections:
1. **Dependency Graph (Tab 1):** An interactive, node-based map showing the relationships and causal links between pods. Nodes glow red when anomalous.
2. **Anomaly Timeline (Tab 2):** A historical swimlane view showing exactly when resources spiked and the severity of the event.
3. **Forecast Alerts (Tab 3):** Predictive warnings showing which pods are trending towards critical failure, complete with ETA countdowns.
4. **NLP Chat / Insights Panel (Right Sidebar):** The AI-generated root-cause summary, and a text box where you can interrogate the LLM about your cluster's health.

---

## 🧪 Running the Test Suite

PodMind comes with a robust set of automated unit tests spanning the agents and API layer.

To run the tests (ensure you have activated your Python virtual environment):

```bash
# Run all tests with short tracebacks
pytest tests/ -v --tb=short

# Run specific agent tests
pytest tests/test_memory_agent.py -v
pytest tests/test_network_agent.py -v
```

---

## 📚 API Documentation

The FastAPI backend automatically generates interactive Swagger documentation.
With the backend running, visit:

👉 **http://localhost:8000/docs**

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/pods` | Fetch all pods with their latest resource metrics |
| `GET` | `/api/graph` | Fetch the node/edge Dependency Graph JSON |
| `GET` | `/api/insights/latest` | Get the most recent LLM-generated root cause analysis |
| `GET` | `/api/anomalies` | Fetch all active anomalies filtered by severity |
| `POST` | `/api/query` | Submit a natural language string and get an LLM response |
| `WS` | `/ws/live` | WebSocket endpoint for real-time metric and graph streaming |

---

*PodMind — Containerized Systems Intelligence. Built for Hackathon 2025.*
