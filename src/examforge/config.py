"""
ExamForge configuration.

Loads settings from (in priority order):
1. CLI arguments (override everything)
2. Environment variables (EXAMFORGE_*)
3. examforge.yaml in the current directory
4. Built-in defaults

Uses pydantic-settings for validation and env-var binding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineConfig(BaseSettings):
    """Configuration for an OCR / layout engine."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    model_name: str = "PaddleOCR-VL-1.6"
    pipeline_version: str = "v1.6"
    api_url: str | None = None
    api_key: str | None = None
    lang: list[str] = Field(default=["en", "hi"])
    use_gpu: bool = False
    timeout_s: float = 60.0
    max_retries: int = 2


class BrowserConfig(BaseSettings):
    """Configuration for the headless browser pool."""

    executable: str | None = None  # None = auto-detect via Playwright
    pool_size: int = 2
    timeout_ms: int = 30_000


class AgentConfig(BaseSettings):
    """Configuration for the LLM agent (disabled in v1)."""

    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    api_key_env: str = "EXAMFORGE_AGENT_API_KEY"
    max_calls_per_page: int = 10
    max_cost_per_run_usd: float = 1.0


class PathConfig(BaseSettings):
    """Configurable paths for run artifacts."""

    runs: Path = Field(default=Path("./runs"))
    ledger: Path = Field(default=Path("./ledger"))
    cache: Path = Field(default=Path("./.cache"))

    @model_validator(mode="after")
    def resolve_paths(self) -> PathConfig:
        self.runs = self.runs.resolve()
        self.ledger = self.ledger.resolve()
        self.cache = self.cache.resolve()
        return self


class ExamForgeConfig(BaseSettings):
    """Root configuration for ExamForge."""

    model_config = SettingsConfigDict(
        env_prefix="EXAMFORGE_",
        env_nested_delimiter="__",
    )

    # Processing mode: "fast" or "max"
    mode: str = "fast"

    # Sub-configs
    engines: dict[str, EngineConfig] = Field(default_factory=lambda: {
        "paddlevl": EngineConfig(model_name="PaddleOCR-VL-1.6", pipeline_version="v1.6"),
        "paddleocr": EngineConfig(model_name="PaddleOCR-VL-1.6", pipeline_version="v1.6"),
        "tesseract": EngineConfig(lang=["eng+hin"]),
    })
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    paths: PathConfig = Field(default_factory=PathConfig)

    # Pipeline behavior
    fail_policy: str = "fail_page"  # "fail_fast", "fail_page", "fail_warn"
    max_pages: int | None = None  # Process only first N pages (for debugging)
    debug: bool = False  # Include provenance attributes in HTML output

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> ExamForgeConfig:
        """
        Load config from YAML file with optional overrides.

        Args:
            config_path: Path to examforge.yaml. If None, looks in CWD.
            overrides: Dict of overrides from CLI flags.

        Returns:
            Validated ExamForgeConfig.
        """
        data: dict[str, Any] = {}

        # Try to load YAML config
        if config_path is None:
            config_path = Path("examforge.yaml")
        if config_path.exists():
            with open(config_path) as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded

        # Apply CLI overrides
        if overrides:
            _deep_merge(data, overrides)

        return cls(**data)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, mutating base."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
