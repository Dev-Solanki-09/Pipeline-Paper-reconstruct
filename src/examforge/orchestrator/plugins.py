"""
Phase 16.4 — Plugin Discovery and Safe Loading.

Discovers third-party plugins from Python entry points:
- examforge.stages
- examforge.validators
- examforge.languages
- examforge.ocr
- examforge.exporters
- examforge.profiles
- examforge.llm
and from local `plugins/` directories.

Incompatible API versions or failing plugins are skipped with a visible warning,
never crashing the pipeline. Errors inside plugin calls are isolated.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from examforge import registry

logger = logging.getLogger(__name__)

SUPPORTED_API_VERSIONS = {"2.0", "2.0.0", "2.x"}

ENTRY_POINT_GROUPS = [
    "examforge.stages",
    "examforge.validators",
    "examforge.languages",
    "examforge.ocr",
    "examforge.exporters",
    "examforge.profiles",
    "examforge.llm",
]


@dataclass
class PluginInfo:
    name: str
    group: str
    api_version: str
    capabilities: list[str] = field(default_factory=list)
    source: str = "entrypoint"
    instance: Any = None


@dataclass
class PluginDiscoveryResult:
    loaded: list[PluginInfo] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)
    conflicts: list[str] = field(default_factory=list)


def is_api_compatible(api_version: str) -> bool:
    """Check if plugin's api_version is compatible with ExamForge 2.0.x."""
    if not api_version:
        return False
    v = api_version.strip()
    return v in SUPPORTED_API_VERSIONS or v.startswith("2.0")


class PluginManager:
    """Manages safe discovery and error-isolated execution of plugins."""

    def __init__(self, plugins_dir: Path | str = "plugins") -> None:
        self.plugins_dir = Path(plugins_dir)

    def discover_all(self) -> PluginDiscoveryResult:
        """Discover from both setuptools/packaging entrypoints and local directory."""
        res = PluginDiscoveryResult()
        self._discover_entrypoints(res)
        self._discover_local_dir(res)
        self._register_loaded(res)
        return res

    def _discover_entrypoints(self, result: PluginDiscoveryResult) -> None:
        try:
            all_eps = importlib.metadata.entry_points()
        except Exception as e:
            logger.warning("Could not read entry points: %s", e)
            return

        for group in ENTRY_POINT_GROUPS:
            # Handle Python 3.10+ select interface vs legacy dict interface
            eps = (
                all_eps.select(group=group)
                if hasattr(all_eps, "select")
                else all_eps.get(group, [])
            )
            for ep in eps:
                try:
                    obj = ep.load()
                    api_ver = getattr(obj, "api_version", getattr(obj, "__api_version__", "2.0.0"))
                    if not is_api_compatible(str(api_ver)):
                        msg = f"Incompatible API version '{api_ver}' (requires 2.0.x)"
                        result.skipped.append((ep.name, msg))
                        logger.warning("Skipping plugin %s: %s", ep.name, msg)
                        continue

                    caps = list(getattr(obj, "capabilities", []))
                    info = PluginInfo(
                        name=ep.name,
                        group=group,
                        api_version=str(api_ver),
                        capabilities=caps,
                        source="entrypoint",
                        instance=obj,
                    )
                    result.loaded.append(info)
                except Exception as e:
                    msg = f"Failed to load entrypoint: {e}"
                    result.skipped.append((ep.name, msg))
                    logger.warning("Skipping plugin %s due to error: %s", ep.name, e)

    def _discover_local_dir(self, result: PluginDiscoveryResult) -> None:
        if not self.plugins_dir.exists() or not self.plugins_dir.is_dir():
            return

        for p in self.plugins_dir.glob("*.py"):
            if p.name.startswith("_"):
                continue
            name = p.stem
            try:
                spec = importlib.util.spec_from_file_location(f"examforge_local_plugin_{name}", p)
                if not spec or not spec.loader:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                api_ver = getattr(mod, "api_version", getattr(mod, "__api_version__", "2.0.0"))
                if not is_api_compatible(str(api_ver)):
                    msg = f"Incompatible API version '{api_ver}' (requires 2.0.x)"
                    result.skipped.append((name, msg))
                    logger.warning("Skipping local plugin %s: %s", name, msg)
                    continue

                group = getattr(mod, "plugin_group", "examforge.stages")
                caps = list(getattr(mod, "capabilities", []))
                info = PluginInfo(
                    name=name,
                    group=group,
                    api_version=str(api_ver),
                    capabilities=caps,
                    source="local",
                    instance=mod,
                )
                result.loaded.append(info)
            except Exception as e:
                msg = f"Failed to load local plugin: {e}"
                result.skipped.append((name, msg))
                logger.warning("Skipping local plugin %s due to error: %s", name, e)

    def _register_loaded(self, result: PluginDiscoveryResult) -> None:
        """Register compatible plugins into the corresponding typed registry."""
        for p in result.loaded:
            group_registry_map = {
                "examforge.stages": registry.stages,
                "examforge.validators": registry.validators,
                "examforge.languages": registry.languages,
                "examforge.ocr": registry.ocr_engines,
                "examforge.exporters": registry.exporters,
                "examforge.profiles": registry.profiles,
                "examforge.llm": registry.llm_providers,
            }
            target_reg = group_registry_map.get(p.group)
            if target_reg:
                if p.name in target_reg:
                    msg = f"Duplicate capability or name '{p.name}' in {p.group}"
                    result.conflicts.append(msg)
                    logger.warning(msg)
                else:
                    try:
                        target_reg.register(
                            p.name,
                            p.instance,
                            capabilities=set(p.capabilities),
                        )
                    except Exception as e:
                        logger.warning("Registration failed for %s: %s", p.name, e)


def safe_call_plugin(plugin_fn: Any, *args: Any, **kwargs: Any) -> tuple[Any, Exception | None]:
    """
    Execute a plugin function with total error isolation.
    Returns (result, None) on success or (None, exception) on failure.
    """
    try:
        return plugin_fn(*args, **kwargs), None
    except Exception as e:
        logger.warning("Isolated exception in plugin execution: %s", e)
        return None, e
