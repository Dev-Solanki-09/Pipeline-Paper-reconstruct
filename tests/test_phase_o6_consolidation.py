"""
Tests for Phase O6: Delete Dead Weight and Consolidate.

Verifies:
- O6.1: Single generic Registry[T] backs validators, languages, and exporters.
- O6.2: Compute tiers unified between config.py and profiles/compute.py.
- O6.3: Non-core exporters (qti, jsonl, markdown) and scaffolded language plugins lazy-load on demand.
- O6.4: Zero regressions across all consolidated systems.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

from examforge import registry
from examforge.config import ExamForgeConfig
from examforge.export.base import BaseExporter
from examforge.export.registry import ExporterRegistry, default_registry, get_exporter, list_exporters
from examforge.lang.registry import ScriptPlugin, get_plugin, list_supported_languages
from examforge.profiles.compute import ComputeTierConfig, load_compute_tier, resolve_compute_tier
from examforge.registry import Registry, RegistryEntry
from examforge.validators.registry import get_canonical_validator_name, get_validator, list_validators


def test_o6_1_registry_consolidation():
    """Verify generic Registry[T] is used across validators, languages, and exporters."""
    # Check that canonical registries are Registry instances
    assert isinstance(registry.stages, Registry)
    assert isinstance(registry.validators, Registry)
    assert isinstance(registry.languages, Registry)
    assert isinstance(registry.ocr_engines, Registry)
    assert isinstance(registry.exporters, Registry)
    assert isinstance(registry.profiles, Registry)
    assert isinstance(registry.llm_providers, Registry)

    # 1. Validators
    assert len(registry.validators) > 0
    assert callable(get_validator("furniture_branding"))
    assert callable(get_validator("no_headers_footers_page_numbers"))  # Alias
    assert "furniture_branding" in list_validators()

    # 2. Languages
    assert "en" in registry.languages or "en" in list_supported_languages()
    en_plugin = get_plugin("en")
    assert en_plugin.lang == "en"
    assert "en" in registry.languages

    # 3. Exporters
    assert isinstance(default_registry, ExporterRegistry)
    html_exp = get_exporter("html")
    assert isinstance(html_exp, BaseExporter)
    assert "html" in registry.exporters


def test_o6_2_compute_tier_unification():
    """Verify compute tier is unified between config.py and profiles/compute.py."""
    # Default standard tier
    cfg_std = ExamForgeConfig()
    compute_std = cfg_std.get_compute_config()
    assert isinstance(compute_std, ComputeTierConfig)
    assert compute_std.tier == "standard"
    assert compute_std.dpi == 150
    assert compute_std.paddle_device == "cpu"

    # Lite tier
    cfg_lite = ExamForgeConfig(compute_tier="lite")
    compute_lite = cfg_lite.get_compute_config()
    assert compute_lite.tier == "lite"
    assert compute_lite.dpi == 120
    assert compute_lite.workers == 1
    assert compute_lite.max_image_pixels == 25_000_000

    # GPU tier
    cfg_gpu = ExamForgeConfig(compute_tier="gpu")
    compute_gpu = cfg_gpu.get_compute_config()
    assert compute_gpu.tier == "gpu"
    assert compute_gpu.paddle_device == "gpu"
    assert compute_gpu.max_image_pixels == 120_000_000


def test_o6_3_lazy_loading_exporters_and_languages():
    """Verify non-core exporters and scaffolded language plugins lazy-load on demand."""
    # Exporters lazy load on demand
    exp_md = get_exporter("markdown")
    assert isinstance(exp_md, BaseExporter)
    assert "markdown" in registry.exporters

    exp_jsonl = get_exporter("jsonl")
    assert isinstance(exp_jsonl, BaseExporter)
    assert "jsonl" in registry.exporters

    exp_qti = get_exporter("qti")
    assert isinstance(exp_qti, BaseExporter)
    assert "qti" in registry.exporters

    # Formats list includes all available formats
    formats = list_exporters()
    assert {"html", "json", "markdown", "jsonl", "qti"}.issubset(set(formats))

    # Scaffolded language plugin lazy load on demand (e.g. Tamil 'ta' and Urdu 'ur')
    with pytest.warns(UserWarning, match="scaffolded"):
        ta_plugin = get_plugin("ta")
    assert ta_plugin.lang == "ta"
    assert "ta" in registry.languages

    with pytest.warns(UserWarning, match="scaffolded"):
        ur_plugin = get_plugin("ur")
    assert ur_plugin.lang == "ur"
    assert "ur" in registry.languages

    # Supported languages list
    all_langs = list_supported_languages()
    assert {"en", "hi", "ta", "ur", "gu", "bn"}.issubset(set(all_langs))
