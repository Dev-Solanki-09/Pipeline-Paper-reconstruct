"""
Language plugin API and script registry.

Provides the ScriptPlugin Protocol, resolution from ProfileSpec,
and script/language detection via Unicode block ranges.
"""

from __future__ import annotations

import re
import unicodedata
import warnings
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from examforge.profiles.schema import ProfileSpec


class NotShipQualityWarning(UserWarning):
    """Raised when a scaffolded language plugin that is not certified ship-quality is used."""


@runtime_checkable
class ScriptPlugin(Protocol):
    """Protocol for language and script handling plugins."""

    lang: str
    script: str
    direction: str  # 'ltr' | 'rtl'
    is_ship_quality: bool
    capabilities: list[str]
    digits_map: dict[str, str]

    def normalize(self, text: str) -> str:
        """Apply script-aware NFC normalization, nukta/matra fixes, etc."""
        ...

    def punctuation_fixes(self, text: str) -> str:
        """Apply script-aware punctuation rules (e.g. danda conversion)."""
        ...

    def split_bilingual(self, text: str, second_lang: str = "hi") -> tuple[str, str]:
        """Split bilingual text into (primary, secondary)."""
        ...

    def font_repair(self, text: str, font_name: str | None = None) -> str:
        """Repair legacy-encoded font text if applicable."""
        ...


from examforge.registry import languages as _CANONICAL_LANG_REGISTRY

_REGISTRY: dict[str, ScriptPlugin] = {}

SCAFFOLDED_LANG_CODES = {"bn", "gu", "kn", "ml", "mr", "pa", "ta", "te", "ur"}


def register_plugin(plugin: ScriptPlugin) -> None:
    """Register a language plugin."""
    lang_key = plugin.lang.lower().strip()
    _REGISTRY[lang_key] = plugin
    _CANONICAL_LANG_REGISTRY.register(
        lang_key,
        plugin,
        capabilities=getattr(plugin, "capabilities", []),
        allow_replace=True,
    )


def get_plugin(lang_code: str) -> ScriptPlugin:
    """
    Get the language plugin for a given ISO language code.

    Raises NotShipQualityWarning if the plugin is scaffolded.
    """
    code = lang_code.lower().strip()

    # Lazy load scaffolded plugin on demand if requested
    if code not in _REGISTRY and code not in _CANONICAL_LANG_REGISTRY and code in SCAFFOLDED_LANG_CODES:
        from examforge.lang.plugins.scaffolded import get_scaffolded_plugins
        for sp in get_scaffolded_plugins():
            if sp.lang.lower().strip() == code:
                register_plugin(sp)
                break

    if code in _CANONICAL_LANG_REGISTRY:
        plugin = _CANONICAL_LANG_REGISTRY.get(code)
    elif code in _REGISTRY:
        plugin = _REGISTRY[code]
    else:
        # Fallback to English if unknown
        code = "en"
        plugin = _CANONICAL_LANG_REGISTRY.get("en") if "en" in _CANONICAL_LANG_REGISTRY else _REGISTRY["en"]

    if not plugin.is_ship_quality:
        warnings.warn(
            f"Plugin for language '{plugin.lang}' ({plugin.script}) is scaffolded and not yet certified ship-quality.",
            category=NotShipQualityWarning,
            stacklevel=2,
        )
    return plugin


def list_supported_languages() -> list[str]:
    """List all registered language codes."""
    all_codes = set(_REGISTRY.keys()) | set(_CANONICAL_LANG_REGISTRY.list()) | SCAFFOLDED_LANG_CODES
    return sorted(all_codes)


def resolve_plugins_for_profile(profile: ProfileSpec) -> list[ScriptPlugin]:
    """Resolve active language plugins from profile.languages."""
    plugins = []
    for l_spec in profile.languages:
        plugins.append(get_plugin(l_spec.code))
    return plugins


# Unicode range patterns for script detection
SCRIPT_BLOCK_RANGES = [
    ("Deva", re.compile(r"[\u0900-\u097F]")),
    ("Beng", re.compile(r"[\u0980-\u09FF]")),
    ("Guru", re.compile(r"[\u0A00-\u0A7F]")),
    ("Gujr", re.compile(r"[\u0A80-\u0AFF]")),
    ("Orya", re.compile(r"[\u0B00-\u0B7F]")),
    ("Taml", re.compile(r"[\u0B80-\u0BFF]")),
    ("Telu", re.compile(r"[\u0C00-\u0C7F]")),
    ("Knda", re.compile(r"[\u0C80-\u0CFF]")),
    ("Mlym", re.compile(r"[\u0D00-\u0D7F]")),
    ("Arab", re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")),
    ("Hani", re.compile(r"[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]")),
    ("Latn", re.compile(r"[A-Za-z]")),
]

SCRIPT_TO_DEFAULT_LANG = {
    "Deva": "hi",
    "Beng": "bn",
    "Guru": "pa",
    "Gujr": "gu",
    "Orya": "or",
    "Taml": "ta",
    "Telu": "te",
    "Knda": "kn",
    "Mlym": "ml",
    "Arab": "ur",
    "Hani": "zh",
    "Latn": "en",
}


def detect_script(text: str) -> str:
    """Detect predominant or distinctive script from Unicode ranges."""
    if not text:
        return "Latn"

    # Count characters per script
    counts: dict[str, int] = {}
    for script_name, pat in SCRIPT_BLOCK_RANGES:
        cnt = len(pat.findall(text))
        if cnt > 0:
            counts[script_name] = cnt

    if not counts:
        return "Latn"

    # Non-Latin scripts take precedence if present
    non_latn = {k: v for k, v in counts.items() if k != "Latn"}
    if non_latn:
        return max(non_latn.items(), key=lambda item: item[1])[0]

    return "Latn"


def detect_lang(text: str) -> str:
    """Detect language code based on detected script."""
    script = detect_script(text)
    # Check for specific Urdu markers in Arabic script (e.g. گ, ے, چ, پ)
    if script == "Arab":
        if re.search(r"[\u06AF\u06D2\u0686\u067E\u0691\u06BE\u0679\u0688]", text):
            return "ur"
    return SCRIPT_TO_DEFAULT_LANG.get(script, "en")


# Auto-register core plugins (scaffolded plugins are lazy-loaded on demand in get_plugin)
def _init_default_plugins():
    from examforge.lang.plugins.en import EnglishPlugin
    from examforge.lang.plugins.hi import HindiPlugin

    register_plugin(EnglishPlugin())
    register_plugin(HindiPlugin())


_init_default_plugins()
