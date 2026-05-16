"""
PodMind — API Routers: Anomalies

SRS §9 compliance: GET /api/anomalies endpoint.
Returns the current anomaly list with severity from the latest insight.
"""

from fastapi import APIRouter, Request
from api.models import APIResponse

router = APIRouter()


@router.get("/anomalies", response_model=APIResponse)
async def get_anomalies(request: Request, severity: str | None = None):
    """
    Get current anomaly list with severity.

    SRS §9: GET /api/anomalies — Current anomaly list with severity.

    Optional query param:
        severity: Filter by severity level (critical, high, medium, low)
    """
    insight_store = request.app.state.insight_store
    latest = await insight_store.get_latest()

    if not latest:
        return APIResponse(data=[])

    anomalies = []
    for cause in latest.root_causes:
        anomaly = {
            "rank": cause.rank,
            "pod": cause.pod,
            "namespace": cause.namespace,
            "resource": cause.resource.value if hasattr(cause.resource, 'value') else str(cause.resource),
            "description": cause.description,
            "severity": cause.severity.value if hasattr(cause.severity, 'value') else str(cause.severity),
            "confidence": cause.confidence,
        }
        anomalies.append(anomaly)

    # Optional severity filter
    if severity:
        severity_lower = severity.lower()
        anomalies = [a for a in anomalies if a["severity"] == severity_lower]

    return APIResponse(data=anomalies)
