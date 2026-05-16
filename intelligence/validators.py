"""
PodMind — LLM Output Validators

Pydantic schema validation of LLM JSON output with error recovery.
Handles common LLM output issues: truncated JSON, extra fields,
type coercion, and malformed enum values.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import ValidationError

from agents.schemas import InsightOutput, Severity, ResourceType

logger = logging.getLogger("podmind.intelligence.validators")


def validate_llm_output(raw_text: str) -> tuple[Optional[InsightOutput], list[str]]:
    """
    Validate and parse raw LLM text into InsightOutput.

    Applies progressive relaxation:
    1. Strict parse (exact schema match)
    2. Lenient parse (fix common issues, use defaults)
    3. Partial parse (extract what we can)

    Args:
        raw_text: Raw text from LLM response.

    Returns:
        Tuple of (InsightOutput or None, list of validation errors).
    """
    errors = []

    # Step 1: Extract JSON from response
    json_text = _extract_json(raw_text)
    if not json_text:
        errors.append("No JSON object found in LLM response")
        return None, errors

    # Step 2: Strict parse
    try:
        data = json.loads(json_text)
        output = InsightOutput.model_validate(data)
        return output, []
    except json.JSONDecodeError as e:
        errors.append(f"JSON parse error: {str(e)}")
    except ValidationError as e:
        errors.append(f"Strict validation failed: {e.error_count()} errors")
        # Try lenient parse
        try:
            data = json.loads(json_text)
            fixed_data = _fix_common_issues(data)
            output = InsightOutput.model_validate(fixed_data)
            errors.append("Fixed with lenient parse")
            return output, errors
        except Exception as e2:
            errors.append(f"Lenient parse also failed: {str(e2)}")

    # Step 3: Partial parse — extract what we can
    try:
        data = json.loads(json_text)
        partial = _partial_parse(data)
        if partial:
            errors.append("Used partial parse — some data may be missing")
            return partial, errors
    except Exception:
        pass

    return None, errors


def _extract_json(text: str) -> Optional[str]:
    """Extract JSON object from text, handling markdown code blocks."""
    text = text.strip()

    # Strip markdown code blocks
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Find JSON boundaries
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return None


def _fix_common_issues(data: dict) -> dict:
    """Fix common LLM output issues."""
    # Fix severity values (LLM might use uppercase)
    valid_severities = {s.value for s in Severity}
    valid_resources = {r.value for r in ResourceType}

    if "root_causes" in data:
        for cause in data["root_causes"]:
            if isinstance(cause.get("severity"), str):
                cause["severity"] = cause["severity"].lower()
                if cause["severity"] not in valid_severities:
                    cause["severity"] = "medium"
            if isinstance(cause.get("resource"), str):
                cause["resource"] = cause["resource"].lower()
                if cause["resource"] not in valid_resources:
                    cause["resource"] = "cpu"
            # Ensure confidence is a float
            if "confidence" in cause:
                try:
                    cause["confidence"] = float(cause["confidence"])
                    cause["confidence"] = max(0.0, min(cause["confidence"], 1.0))
                except (ValueError, TypeError):
                    cause["confidence"] = 0.5

    if "recommendations" in data:
        for rec in data["recommendations"]:
            if isinstance(rec.get("priority"), str):
                rec["priority"] = rec["priority"].lower().replace(" ", "-")

    if "forecast_alerts" in data:
        for alert in data["forecast_alerts"]:
            if isinstance(alert.get("resource"), str):
                alert["resource"] = alert["resource"].lower()
            if "eta_minutes" in alert:
                try:
                    alert["eta_minutes"] = float(alert["eta_minutes"])
                except (ValueError, TypeError):
                    alert["eta_minutes"] = 60.0

    return data


def _partial_parse(data: dict) -> Optional[InsightOutput]:
    """Extract whatever valid fields we can from the data."""
    try:
        return InsightOutput(
            summary=data.get("summary", "Partial analysis available"),
            dependency_narrative=data.get("dependency_narrative", ""),
            root_causes=[],
            recommendations=[],
            forecast_alerts=[],
        )
    except Exception:
        return None
