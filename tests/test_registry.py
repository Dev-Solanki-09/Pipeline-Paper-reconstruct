"""Tests for examforge.registry."""

from __future__ import annotations

import pytest

from examforge.registry import (
    Registry,
    RegistryDuplicateError,
    RegistryNotFoundError,
    exporters,
    languages,
    llm_providers,
    ocr_engines,
    profiles,
    stages,
    validators,
)


def test_registry_register_and_get():
    reg: Registry[str] = Registry("test_registry")
    reg.register("alpha", "Alpha Value", version="1.0.0", capabilities={"read"})

    assert reg.get("alpha") == "Alpha Value"
    entry = reg.get_entry("alpha")
    assert entry.name == "alpha"
    assert entry.obj == "Alpha Value"
    assert entry.version == "1.0.0"
    assert "read" in entry.capabilities
    assert "alpha" in reg
    assert reg.list() == ["alpha"]
    assert reg.keys() == ["alpha"]


def test_registry_decorator_usage():
    reg: Registry[type] = Registry("classes")

    @reg.register("my_class", capabilities={"exec"})
    class MyClass:
        pass

    assert reg.get("my_class") is MyClass
    assert reg.get_entry("my_class").capabilities == {"exec"}


def test_registry_duplicate_registration_fails():
    reg: Registry[int] = Registry("numbers")
    reg.register("num1", 42)

    with pytest.raises(RegistryDuplicateError) as exc_info:
        reg.register("num1", 99)

    assert "already registered" in str(exc_info.value)
    assert "num1" in str(exc_info.value)


def test_registry_not_found_raises():
    reg: Registry[str] = Registry("items")
    with pytest.raises(RegistryNotFoundError) as exc_info:
        reg.get("nonexistent")

    assert "nonexistent" in str(exc_info.value)
    assert "items" in str(exc_info.value)


def test_registry_capabilities_search():
    reg: Registry[str] = Registry("tools")
    reg.register("tool_a", "A", capabilities={"gpu", "ocr"})
    reg.register("tool_b", "B", capabilities={"cpu", "ocr"})
    reg.register("tool_c", "C", capabilities={"gpu"})

    ocr_tools = [e.name for e in reg.find_by_capability("ocr")]
    assert sorted(ocr_tools) == ["tool_a", "tool_b"]

    gpu_tools = [e.name for e in reg.find_by_capability("gpu")]
    assert sorted(gpu_tools) == ["tool_a", "tool_c"]

    missing = reg.find_by_capability("quantum")
    assert missing == []


def test_global_registries_exist():
    assert stages.name == "stages"
    assert validators.name == "validators"
    assert languages.name == "languages"
    assert ocr_engines.name == "ocr_engines"
    assert exporters.name == "exporters"
    assert profiles.name == "profiles"
    assert llm_providers.name == "llm_providers"
