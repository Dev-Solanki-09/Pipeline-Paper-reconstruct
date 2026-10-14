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


from examforge.profiles.compute import ComputeTierConfig, resolve_compute_tier

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

    # Feature flags (all v2 feature flags active for release)
    flags: dict[str, bool] = Field(default_factory=lambda: {
        "verifiers_v2": True,
        "layout_v2": True,
        "figures_v2": True,
        "clean_v2": True,
        "lang_v2": True,
        "answers": True,
        "s7_repair": True,
        "bank": True,
        "autoprofile": True,
        "lessons": True,
        "template_v2": True,
        "exporters": True,
    })

    # Pipeline behavior
    fail_policy: str = "fail_page"  # "fail_fast", "fail_page", "fail_warn"
    checkpoint_tier: str = "major"  # "all", "major", "none"
    max_pages: int | None = None  # Process only first N pages (for debugging)
    debug: bool = False  # Include provenance attributes in HTML output
    bank_path: Path = Field(default_factory=lambda: Path("data/bank/bank.db"))
    profile_cache_path: Path = Field(
        default_factory=lambda: Path("data/profiles/profile_cache.sqlite")
    )
    lessons_path: Path = Field(
        default_factory=lambda: Path("data/lessons/lessons.jsonl")
    )
    proposals_dir: Path = Field(default_factory=lambda: Path("proposals"))

    # Unified compute tier configuration (Phase O6.2)
    compute_tier: str = "standard"  # "lite", "standard", "gpu"

    def get_compute_config(self) -> ComputeTierConfig:
        """Resolve unified compute tier configuration."""
        return resolve_compute_tier(self.compute_tier)

    def flag(self, name: str, default: bool = False) -> bool:
        """Check whether a feature flag is enabled."""
        return self.flags.get(name, default)

    def set_flag(self, name: str, value: bool) -> None:
        """Set a feature flag value."""
        self.flags[name] = value

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
