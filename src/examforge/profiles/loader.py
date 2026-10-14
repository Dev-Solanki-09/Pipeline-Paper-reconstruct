"""
Profile loader and inheritance resolution engine for ExamForge v2.

Handles:
- Loading YAML profiles from files, strings, or built-in templates.
- Resolving inheritance chains: base -> extends... -> profile -> CLI overrides.
- Deep-merging dictionaries with deterministic list semantics ($append / $replace).
- Formatting human-readable validation errors with YAML file and line numbers.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

import yaml
from pydantic import ValidationError

from examforge.profiles.schema import ExamProfile
from examforge.registry import profiles as profiles_registry

logger = logging.getLogger(__name__)

BUILTIN_PROFILES_DIR = Path(__file__).parent / "builtin"


class ProfileLoadError(Exception):
    """Raised when a profile fails to load, resolve, or validate."""


class LineTrackingLoader(yaml.SafeLoader):
    """YAML SafeLoader that records line numbers for dictionary keys."""


def _construct_mapping_with_lines(
    loader: LineTrackingLoader,
    node: yaml.MappingNode,
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    line_map: dict[str, int] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=False)
        val = loader.construct_object(value_node, deep=False)
        mapping[key] = val
        line_map[str(key)] = key_node.start_mark.line + 1

    mapping["__line_map__"] = line_map
    mapping["__line__"] = node.start_mark.line + 1
    return mapping


LineTrackingLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_with_lines,
)


def deep_merge(base: Any, override: Any) -> Any:
    """
    Recursively merge `override` onto `base`.

    Semantics:
    - Dicts are recursively merged.
    - If override is a dict with '$append', its contents are appended to base list.
    - If override is a dict with '$replace', its contents replace base list.
    - Otherwise, override replaces base.
    """
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for k, v in override.items():
            if k == "__line_map__" or k == "__line__":
                merged[k] = v
                continue
            if k in merged:
                merged[k] = deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    if isinstance(override, dict) and "$append" in override:
        base_list = list(base) if isinstance(base, list) else []
        return base_list + list(override["$append"])

    if isinstance(override, dict) and "$replace" in override:
        return list(override["$replace"])

    return override


def _clean_internal_metadata(data: Any) -> Any:
    """Remove line tracking metadata keys before Pydantic validation."""
    if isinstance(data, dict):
        return {
            k: _clean_internal_metadata(v) for k, v in data.items() if not k.startswith("__line")
        }
    if isinstance(data, list):
        return [_clean_internal_metadata(item) for item in data]
    return data


def _find_field_line(raw_data: Any, loc: tuple[str | int, ...]) -> int | None:
    """Traverse line tracking metadata to find the line number for a field path."""
    curr = raw_data
    last_line = curr.get("__line__") if isinstance(curr, dict) else None

    for part in loc:
        if isinstance(curr, dict):
            line_map = curr.get("__line_map__", {})
            if str(part) in line_map:
                last_line = line_map[str(part)]
            curr = curr.get(part)
        else:
            break

    return last_line


class ProfileLoader:
    """Loads and resolves declarative ExamProfiles with inheritance."""

    def __init__(self, search_paths: list[Path] | None = None):
        self.search_paths = list(search_paths or [])
        if BUILTIN_PROFILES_DIR not in self.search_paths:
            self.search_paths.append(BUILTIN_PROFILES_DIR)

    def find_profile_file(self, profile_id: str) -> Path:
        """Find a profile YAML file by ID or path."""
        candidate = Path(profile_id)
        if candidate.is_file():
            return candidate

        # Try with .yaml and .yml extensions across search paths
        for base in self.search_paths:
            for ext in (".yaml", ".yml", ""):
                p = base / f"{profile_id}{ext}"
                if p.is_file():
                    return p

        raise ProfileLoadError(
            f"Profile '{profile_id}' not found in search paths: {self.search_paths}"
        )

    def load_raw_yaml(self, path: Path) -> dict[str, Any]:
        """Read YAML file with line number annotations."""
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.load(content, Loader=LineTrackingLoader)  # noqa: S506
            if not isinstance(data, dict):
                raise ProfileLoadError(f"Profile file '{path}' must contain a YAML mapping.")
            return data
        except yaml.YAMLError as exc:
            raise ProfileLoadError(f"YAML syntax error in '{path}': {exc}") from exc

    def load_raw_yaml_str(self, content: str, source_name: str = "<string>") -> dict[str, Any]:
        """Parse YAML string with line number annotations."""
        try:
            data = yaml.load(content, Loader=LineTrackingLoader)  # noqa: S506
            if not isinstance(data, dict):
                raise ProfileLoadError(f"Profile '{source_name}' must contain a YAML mapping.")
            return data
        except yaml.YAMLError as exc:
            raise ProfileLoadError(f"YAML syntax error in '{source_name}': {exc}") from exc

    def resolve_inheritance(
        self,
        raw_target: dict[str, Any],
        seen_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Recursively resolve inheritance chain:
        base -> parent -> target.
        Detects circular inheritance cycles.
        """
        seen = list(seen_ids or [])
        target_id = raw_target.get("id", "unnamed")

        if target_id in seen:
            cycle = " -> ".join(seen + [target_id])
            raise ProfileLoadError(f"Circular profile inheritance detected: {cycle}")

        seen.append(target_id)

        extends_list = raw_target.get("extends", [])
        if isinstance(extends_list, str):
            extends_list = [extends_list]

        # If not "base" and "base" not in extends, base is implicitly the root
        accumulated: dict[str, Any] = {}
        if target_id != "base" and "base" not in extends_list and BUILTIN_PROFILES_DIR.is_dir():
            base_path = BUILTIN_PROFILES_DIR / "base.yaml"
            if base_path.is_file() and "base" not in seen:
                base_raw = self.load_raw_yaml(base_path)
                accumulated = self.resolve_inheritance(base_raw, seen)

        # Merge ancestors in declared order
        for ancestor_id in extends_list:
            ancestor_path = self.find_profile_file(ancestor_id)
            ancestor_raw = self.load_raw_yaml(ancestor_path)
            ancestor_resolved = self.resolve_inheritance(ancestor_raw, seen)
            accumulated = deep_merge(accumulated, ancestor_resolved)

        # Merge target profile on top
        return deep_merge(accumulated, raw_target)

    def load(
        self,
        profile_id_or_path: str | Path,
        cli_overrides: dict[str, Any] | None = None,
    ) -> ExamProfile:
        """
        Load, inherit, and validate an ExamProfile.
        """
        if isinstance(profile_id_or_path, str) and (
            profile_id_or_path.endswith(".yaml") or profile_id_or_path.endswith(".yml")
        ):
            path = Path(profile_id_or_path)
        else:
            path = self.find_profile_file(str(profile_id_or_path))

        raw_data = self.load_raw_yaml(path)
        resolved_raw = self.resolve_inheritance(raw_data)

        if cli_overrides:
            resolved_raw = deep_merge(resolved_raw, cli_overrides)

        # Validate with Pydantic, capturing clean errors with line numbers
        cleaned = _clean_internal_metadata(resolved_raw)

        try:
            profile = ExamProfile.model_validate(cleaned)
        except ValidationError as exc:
            formatted_errors = []
            for err in exc.errors():
                loc = err["loc"]
                msg = err["msg"]
                line = _find_field_line(resolved_raw, loc)
                loc_str = ".".join(str(p) for p in loc)
                if line:
                    formatted_errors.append(f"{path.name}:{line}: field '{loc_str}' {msg}")
                else:
                    formatted_errors.append(f"{path.name}: field '{loc_str}' {msg}")

            raise ProfileLoadError(
                f"Profile validation failed for '{path.name}':\n  " + "\n  ".join(formatted_errors)
            ) from exc

        _vet_profile_regexes(profile, str(path.name))
        return profile


_DANGEROUS_NESTED_QUANTIFIER = re.compile(r"\([^)]*[\+\*]\)[\+\*]")


def _vet_profile_regexes(profile: ExamProfile, source_name: str) -> None:
    """Pre-compile and vet profile regexes for syntax and ReDoS safety (O1.8)."""
    patterns_to_check: list[str] = []
    if profile.numbering and hasattr(profile.numbering, "patterns"):
        patterns_to_check.extend(profile.numbering.patterns or [])
    if hasattr(profile, "sections") and profile.sections:
        patterns_to_check.extend(getattr(profile.sections, "custom_sections", []) or [])

    for pat in patterns_to_check:
        if not pat or not isinstance(pat, str):
            continue
        if _DANGEROUS_NESTED_QUANTIFIER.search(pat):
            raise ProfileLoadError(
                f"Catastrophic ReDoS risk detected in pattern '{pat}' in profile '{source_name}'"
            )
        try:
            re.compile(pat)
        except re.error as exc:
            raise ProfileLoadError(
                f"Invalid regex '{pat}' in profile '{source_name}': {exc}"
            ) from exc


    def load_all_builtins(self) -> dict[str, ExamProfile]:
        """Load and register all built-in profiles."""
        if not BUILTIN_PROFILES_DIR.is_dir():
            return {}

        results: dict[str, ExamProfile] = {}
        for p in sorted(BUILTIN_PROFILES_DIR.glob("*.yaml")):
            profile_id = p.stem
            try:
                prof = self.load(profile_id)
                results[prof.id] = prof
                # Register if not already registered
                if prof.id not in profiles_registry:
                    profiles_registry.register(
                        prof.id,
                        prof,
                        version=prof.profile_version,
                        capabilities=prof.requires,
                        tags={"maturity": prof.maturity},
                    )
            except Exception as exc:
                logger.warning("Failed to load built-in profile '%s': %s", profile_id, exc)

        return results


# Default global loader instance
loader = ProfileLoader()
