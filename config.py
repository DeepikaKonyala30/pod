"""
PodMind — Shared Configuration Module

Centralized configuration using Pydantic Settings for type-safe,
environment-variable-driven configuration across all PodMind components.

Usage:
    from config import settings
    redis_url = settings.redis_url
    llm_tier = settings.podmind_llm_tier
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PodMindSettings(BaseSettings):
    """
    All PodMind configuration, loaded from environment variables or .env file.
    Organized by component layer for clarity.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # LLM Configuration
    # -------------------------------------------------------------------------
    podmind_llm_tier: int = Field(
        default=1,
        ge=1,
        le=3,
        description="LLM tier: 1=Claude (best), 2=GPT-4o (cost-opt), 3=Ollama (offline)",
    )
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic Claude API key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama server URL")
    ollama_model: str = Field(default="llama3:8b", description="Ollama model name")

    # -------------------------------------------------------------------------
    # Redis Configuration
    # -------------------------------------------------------------------------
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_max_connections: int = Field(default=20, ge=5, le=100)

    # -------------------------------------------------------------------------
    # Prometheus Configuration
    # -------------------------------------------------------------------------
    prometheus_url: str = Field(
        default="http://localhost:9090", description="Prometheus server URL"
    )

    # -------------------------------------------------------------------------
    # Kubernetes Configuration
    # -------------------------------------------------------------------------
    k8s_in_cluster: bool = Field(
        default=False, description="Use in-cluster K8s config (ServiceAccount)"
    )
    kubeconfig: Optional[str] = Field(default=None, description="Path to kubeconfig file")

    # -------------------------------------------------------------------------
    # Collection Intervals (seconds)
    # -------------------------------------------------------------------------
    collection_interval_fast: int = Field(default=5, ge=1, le=60, description="CPU/Memory interval")
    collection_interval_medium: int = Field(default=10, ge=5, le=120, description="PVC/Network interval")
    collection_interval_slow: int = Field(default=30, ge=10, le=300, description="Metadata interval")
    collection_interval_logs: int = Field(default=60, ge=30, le=600, description="Log collection interval")

    # -------------------------------------------------------------------------
    # Agent Configuration
    # -------------------------------------------------------------------------
    analysis_interval: int = Field(default=30, ge=10, le=300, description="Agent cycle interval (sec)")
    anomaly_contamination: float = Field(
        default=0.1, ge=0.01, le=0.5, description="Isolation Forest contamination factor"
    )
    granger_max_lag: int = Field(default=6, ge=1, le=20, description="Max lag for Granger test (samples)")
    granger_p_threshold: float = Field(default=0.05, ge=0.001, le=0.1, description="Granger significance")
    memory_leak_slope_threshold: float = Field(
        default=0.005, ge=0.001, le=0.05, description="Memory leak slope (%/min)"
    )
    cpu_throttle_threshold: float = Field(default=0.15, ge=0.05, le=0.5, description="CPU throttle ratio")
    oom_risk_threshold: float = Field(default=0.85, ge=0.5, le=0.99, description="OOM risk threshold")

    # -------------------------------------------------------------------------
    # API Server Configuration
    # -------------------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", description="API bind host")
    api_port: int = Field(default=8000, ge=1024, le=65535, description="API bind port")
    ws_push_interval: int = Field(default=5, ge=1, le=30, description="WebSocket push cadence (sec)")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated CORS origins",
    )

    # -------------------------------------------------------------------------
    # Data Retention
    # -------------------------------------------------------------------------
    metric_retention_hours: int = Field(default=24, ge=1, le=168, description="Redis TS retention (hours)")
    insight_retention_count: int = Field(default=100, ge=10, le=1000, description="Max stored insights")

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")
    log_format: str = Field(default="json", description="Log format: json or text")

    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def llm_tier(self) -> int:
        """Alias for podmind_llm_tier for convenient access."""
        return self.podmind_llm_tier

    @property
    def metric_retention_ms(self) -> int:
        """Redis TimeSeries retention in milliseconds."""
        return self.metric_retention_hours * 3600 * 1000

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return upper


@lru_cache(maxsize=1)
def get_settings() -> PodMindSettings:
    """
    Singleton factory for PodMind settings.
    Cached so .env is only parsed once per process.
    """
    return PodMindSettings()


# Convenience alias for direct import: `from config import settings`
settings = get_settings()
