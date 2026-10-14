"""ExamForge Language Plugin Architecture."""

from __future__ import annotations

from examforge.lang.registry import (
    NotShipQualityWarning,
    ScriptPlugin,
    detect_lang,
    detect_script,
    get_plugin,
    list_supported_languages,
    register_plugin,
    resolve_plugins_for_profile,
)

__all__ = [
    "NotShipQualityWarning",
    "ScriptPlugin",
    "detect_lang",
    "detect_script",
    "get_plugin",
    "list_supported_languages",
    "register_plugin",
    "resolve_plugins_for_profile",
]
