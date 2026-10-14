"""
Phase 14.6 & O6.1/O6.2 — Exporter Registry.
Backed by canonical generic Registry[BaseExporter] with lazy loader support.
"""

from __future__ import annotations

from typing import Callable

from examforge.export.base import BaseExporter
from examforge.registry import exporters as _CANONICAL_EXPORTERS


class ExporterRegistry:
    """Registry managing available ExamDocument exporters with lazy loading."""

    def __init__(self) -> None:
        self._exporters: dict[str, type[BaseExporter]] = {}
        self._instances: dict[str, BaseExporter] = {}
        self._lazy_loaders: dict[str, Callable[[], type[BaseExporter]]] = {
            "html": lambda: __import__("examforge.export.html", fromlist=["HTMLExporter"]).HTMLExporter,
            "json": lambda: __import__("examforge.export.json", fromlist=["JSONExporter"]).JSONExporter,
            "markdown": lambda: __import__("examforge.export.markdown", fromlist=["MarkdownExporter"]).MarkdownExporter,
            "md": lambda: __import__("examforge.export.markdown", fromlist=["MarkdownExporter"]).MarkdownExporter,
            "jsonl": lambda: __import__("examforge.export.jsonl", fromlist=["JSONLExporter"]).JSONLExporter,
            "qti": lambda: __import__("examforge.export.qti", fromlist=["QTIExporter"]).QTIExporter,
        }

    def register(self, format_name: str, exporter_cls: type[BaseExporter]) -> None:
        key = format_name.lower().strip()
        self._exporters[key] = exporter_cls
        self._instances.pop(key, None)
        _CANONICAL_EXPORTERS.register(key, exporter_cls, allow_replace=True)

    def get(self, format_name: str) -> BaseExporter:
        key = format_name.lower().strip()
        if key not in self._exporters and key in self._lazy_loaders:
            cls = self._lazy_loaders[key]()
            self.register(key, cls)

        if key not in self._exporters:
            available = ", ".join(self.list_formats())
            raise KeyError(f"Unknown exporter '{format_name}'. Available: {available}")
        if key not in self._instances:
            self._instances[key] = self._exporters[key]()
        return self._instances[key]

    def list_formats(self) -> list[str]:
        all_formats = set(self._exporters.keys()) | set(self._lazy_loaders.keys()) | set(_CANONICAL_EXPORTERS.list())
        return sorted(list(all_formats))


default_registry = ExporterRegistry()


def get_exporter(format_name: str) -> BaseExporter:
    """Convenience helper to retrieve an exporter by format name."""
    return default_registry.get(format_name)


def list_exporters() -> list[str]:
    """Convenience helper to list all registered exporter names."""
    return default_registry.list_formats()
