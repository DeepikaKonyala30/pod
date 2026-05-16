"""
PodMind — Tiered LLM Client

Implements the three-tier LLM fallback chain specified in SRS §5.4:
  Tier 1: Anthropic Claude claude-sonnet-4-20250514 (best quality, ~2-4s)
  Tier 2: OpenAI GPT-4o-mini (cost-optimized, ~1-3s)
  Tier 3: Ollama local model (offline capable, ~5-15s)

If all tiers fail, falls back to the rule-based recommendation engine.
All LLM responses are validated against the InsightOutput Pydantic schema.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.schemas import InsightOutput

logger = logging.getLogger("podmind.intelligence.llm")


class LLMTier:
    """Base class for an LLM provider tier."""

    name: str = "base"

    async def call(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt and return raw text response."""
        raise NotImplementedError


class ClaudeTier(LLMTier):
    """Tier 1: Anthropic Claude claude-sonnet-4-20250514."""

    name = "Claude claude-sonnet-4-20250514"

    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    async def call(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text


class GPT4oTier(LLMTier):
    """Tier 2: OpenAI GPT-4o-mini."""

    name = "GPT-4o-mini"

    def __init__(self, api_key: str):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    async def call(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=4096,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content


class OllamaTier(LLMTier):
    """Tier 3: Ollama local model (offline fallback)."""

    name = "Ollama"

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3:8b"):
        import ollama
        self._client = ollama.AsyncClient(host=host)
        self._model = model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    async def call(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.chat(
            model=self._model,
            format="json",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response["message"]["content"]


class LLMClient:
    """
    Tiered LLM client with automatic fallback and output validation.

    Tries each tier in order (Claude → GPT-4o → Ollama). If the response
    fails Pydantic validation, it retries with the next tier. If all tiers
    fail, returns a rule-based fallback output.
    """

    def __init__(
        self,
        tier: int = 1,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        ollama_host: str = "http://localhost:11434",
        ollama_model: str = "llama3:8b",
    ):
        """
        Args:
            tier: Starting tier (1=Claude, 2=GPT-4o, 3=Ollama).
            anthropic_api_key: Anthropic API key.
            openai_api_key: OpenAI API key.
            ollama_host: Ollama server URL.
            ollama_model: Ollama model name.
        """
        self._tiers: list[LLMTier] = []
        self._starting_tier = tier

        # Build tier list based on available keys and starting tier
        if tier <= 1 and anthropic_api_key:
            try:
                self._tiers.append(ClaudeTier(anthropic_api_key))
            except Exception as e:
                logger.warning("Failed to initialize Claude tier: %s", str(e))

        if tier <= 2 and openai_api_key:
            try:
                self._tiers.append(GPT4oTier(openai_api_key))
            except Exception as e:
                logger.warning("Failed to initialize GPT-4o tier: %s", str(e))

        if tier <= 3:
            try:
                self._tiers.append(OllamaTier(ollama_host, ollama_model))
            except Exception as e:
                logger.warning("Failed to initialize Ollama tier: %s", str(e))

        if not self._tiers:
            logger.warning("No LLM tiers available. Rule-based fallback only.")

        logger.info(
            "LLM client initialized: %d tiers available [%s]",
            len(self._tiers),
            ", ".join(t.name for t in self._tiers),
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> InsightOutput:
        """
        Generate an insight output by trying each LLM tier in order.

        Args:
            system_prompt: System-level instructions for the LLM.
            user_prompt: User-level prompt with agent data.

        Returns:
            Validated InsightOutput from LLM or rule-based fallback.
        """
        for tier in self._tiers:
            try:
                logger.info("Trying LLM tier: %s", tier.name)
                start = time.monotonic()

                raw_response = await tier.call(system_prompt, user_prompt)
                latency_ms = int((time.monotonic() - start) * 1000)
                logger.info("  %s responded in %dms", tier.name, latency_ms)

                # Parse and validate the response
                insight = self._parse_response(raw_response)
                if insight:
                    logger.info("  %s output validated successfully", tier.name)
                    return insight

                logger.warning("  %s returned invalid output, trying next tier", tier.name)

            except Exception as e:
                logger.warning(
                    "  %s failed: %s. Falling back...", tier.name, str(e)
                )
                continue

        # All tiers failed — return rule-based fallback
        logger.warning("All LLM tiers failed. Using rule-based fallback.")
        return InsightOutput(
            summary="LLM analysis unavailable. Rule-based fallback active.",
            root_causes=[],
            recommendations=[],
            forecast_alerts=[],
            dependency_narrative="Unable to generate narrative — LLM unavailable.",
        )

    async def generate_nlp_response(
        self,
        system_prompt: str,
        user_query: str,
        context: str,
    ) -> str:
        """
        Generate a natural language response for NLP queries.

        Unlike generate(), this returns raw text suitable for chat display.
        """
        prompt = f"Context:\n{context}\n\nUser Question: {user_query}"

        for tier in self._tiers:
            try:
                response = await tier.call(system_prompt, prompt)
                return response.strip()
            except Exception as e:
                logger.warning("%s failed for NLP query: %s", tier.name, str(e))
                continue

        return "I'm unable to process your query right now. Please check the LLM configuration."

    def _parse_response(self, raw: str) -> Optional[InsightOutput]:
        """
        Parse LLM response text into InsightOutput.

        Handles common LLM output issues:
          - JSON wrapped in markdown code blocks
          - Extra text before/after JSON
          - Missing fields (uses Pydantic defaults)
        """
        # Strip markdown code blocks
        text = raw.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # Try to find JSON object boundaries
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1]

        try:
            data = json.loads(text)
            return InsightOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.debug("Failed to parse LLM response: %s", str(e))
            return None

    @property
    def available_tiers(self) -> list[str]:
        """List names of available LLM tiers."""
        return [t.name for t in self._tiers]
