"""
PodMind — API Integration Tests

Tests the FastAPI endpoints using httpx AsyncClient.
Mocks out Redis dependencies to ensure fast, deterministic tests.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from api.main import app
from api.models import SystemHealth
from agents.schemas import InsightOutput, RootCause, Recommendation, DependencyGraph

# =============================================================================
# Mocks
# =============================================================================

class MockRedisReader:
    async def is_healthy(self) -> bool:
        return True
        
    async def get_pod_metadata(self) -> list[dict]:
        return [{"name": "test-pod", "namespace": "default"}]
        
    async def get_pvc_mapping(self) -> dict:
        return {"default:test-pod": ["test-pvc"]}

class MockInsightStore:
    async def get_latest(self) -> InsightOutput:
        return InsightOutput(
            root_causes=[
                RootCause(rank=1, pod="test-pod", namespace="default", 
                          resource="cpu", description="Test", severity="high", confidence=0.9)
            ],
            recommendations=[
                Recommendation(pod="test-pod", namespace="default", 
                               action="Fix it", priority="immediate", rationale="Testing")
            ],
            forecast_alerts=[],
            dependency_narrative="Test narrative",
            summary="Test summary"
        )
        
    async def get_history_with_summaries(self, limit: int = 10) -> list[dict]:
        return [{"id": "1234", "timestamp": "2025-06-01T00:00:00Z", "summary": "Test"}]
        
    async def count(self) -> int:
        return 1

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_app():
    """Create a FastAPI instance with mocked dependencies."""
    app.state.redis_reader = MockRedisReader()
    app.state.insight_store = MockInsightStore()
    return app

@pytest.fixture
async def client(test_app: FastAPI):
    """Async HTTP client for testing."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

# =============================================================================
# Tests
# =============================================================================

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test GET /health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["redis_connected"] is True
    assert "llm_tiers_available" in data

@pytest.mark.asyncio
async def test_get_pods(client: AsyncClient):
    """Test GET /api/pods endpoint."""
    response = await client.get("/api/pods")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 1
    assert data["data"][0]["name"] == "test-pod"

@pytest.mark.asyncio
async def test_get_graph(client: AsyncClient):
    """Test GET /api/graph endpoint."""
    response = await client.get("/api/graph")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "nodes" in data["data"]
    assert "edges" in data["data"]

@pytest.mark.asyncio
async def test_get_latest_insight(client: AsyncClient):
    """Test GET /api/insights/latest endpoint."""
    response = await client.get("/api/insights/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["summary"] == "Test summary"
    assert len(data["data"]["root_causes"]) == 1

@pytest.mark.asyncio
async def test_get_pvcs(client: AsyncClient):
    """Test GET /api/pvcs endpoint."""
    response = await client.get("/api/pvcs")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["default:test-pod"] == ["test-pvc"]
