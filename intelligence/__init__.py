"""
PodMind — LLM Intelligence Layer Package

LLM-powered reasoning that synthesizes agent outputs into actionable
insights, root-cause narratives, and concrete recommendations.

Components:
    - llm_client: Tiered LLM interface (Claude → GPT-4o → Ollama) with fallback
    - prompt_templates: Jinja2-based structured prompts for SRE analysis
    - recommendation_engine: Post-LLM ranking, deduplication, priority assignment
    - insight_store: Redis-backed insight history with TTL and query support
    - validators: Pydantic schema validation of LLM JSON output with error recovery
    - rule_engine: Deterministic rule-based fallback when all LLMs fail (NFR-04)
"""

