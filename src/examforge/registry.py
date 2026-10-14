"""
Typed registry system for ExamForge v2.

Provides centralized, capability-aware registries for:
- stages
- validators
- languages
- ocr_engines
- exporters
- profiles
- llm_providers
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    TypeVar,
    overload,
)

T = TypeVar("T")


class RegistryError(Exception):
    """Base error for registry operations."""


class RegistryDuplicateError(RegistryError):
    """Raised when registering an item with an existing name."""


class RegistryNotFoundError(RegistryError, KeyError):
    """Raised when looking up an unregistered item."""


@dataclass(frozen=True)
class RegistryEntry(Generic[T]):
    """Metadata wrapper for a registered object."""

    name: str
    obj: T
    version: str = "1.0.0"
    capabilities: frozenset[str] = field(default_factory=frozenset)
    tags: dict[str, Any] = field(default_factory=dict)


class Registry(Generic[T]):
    """
    Typed, capability-aware registry with strict duplicate detection.

    Supports both direct registration and decorator-based registration.
    """

    def __init__(self, name: str):
        self.name = name
        self._entries: dict[str, RegistryEntry[T]] = {}

    @overload
    def register(
        self,
        name: str,
        obj: T,
        *,
        version: str = "1.0.0",
        capabilities: Iterable[str] | None = None,
        tags: dict[str, Any] | None = None,
    ) -> T:
        ...

    @overload
    def register(
        self,
        name: str,
        obj: None = None,
        *,
        version: str = "1.0.0",
        capabilities: Iterable[str] | None = None,
        tags: dict[str, Any] | None = None,
    ) -> Callable[[T], T]:
        ...

    def register(
        self,
        name: str,
        obj: T | None = None,
        *,
        version: str = "1.0.0",
        capabilities: Iterable[str] | None = None,
        tags: dict[str, Any] | None = None,
        allow_replace: bool = False,
    ) -> T | Callable[[T], T]:
        """
        Register an object or return a decorator to register it.

        Raises:
            RegistryDuplicateError: If an object is already registered under `name` and allow_replace is False.
        """
        caps = frozenset(capabilities or ())
        tag_dict = dict(tags or {})

        def _do_register(target: T) -> T:
            if name in self._entries and not allow_replace:
                raise RegistryDuplicateError(
                    f"Item '{name}' is already registered in registry '{self.name}'."
                )
            entry = RegistryEntry(
                name=name,
                obj=target,
                version=version,
                capabilities=caps,
                tags=tag_dict,
            )
            self._entries[name] = entry
            return target

        if obj is not None:
            return _do_register(obj)

        return _do_register

    def get(self, name: str) -> T:
        """
        Get registered object by name.

        Raises:
            RegistryNotFoundError: If `name` is not in this registry.
        """
        entry = self._entries.get(name)
        if entry is None:
            raise RegistryNotFoundError(
                f"Item '{name}' not found in registry '{self.name}'. Available: {self.list()}"
            )
        return entry.obj

    def get_entry(self, name: str) -> RegistryEntry[T]:
        """
        Get full RegistryEntry metadata by name.

        Raises:
            RegistryNotFoundError: If `name` is not in this registry.
        """
        entry = self._entries.get(name)
        if entry is None:
            raise RegistryNotFoundError(
                f"Item '{name}' not found in registry '{self.name}'. Available: {self.list()}"
            )
        return entry

    def list(self) -> list[str]:
        """Return sorted list of registered names."""
        return sorted(self._entries.keys())

    def keys(self) -> list[str]:
        """Return sorted list of registered names."""
        return self.list()

    def values(self) -> list[T]:
        """Return all registered objects in sorted order by name."""
        return [self._entries[k].obj for k in self.list()]

    def items(self) -> list[tuple[str, T]]:
        """Return all (name, object) pairs in sorted order by name."""
        return [(k, self._entries[k].obj) for k in self.list()]

    def entries(self) -> list[RegistryEntry[T]]:
        """Return all RegistryEntry instances in sorted order by name."""
        return [self._entries[k] for k in self.list()]

    def find_by_capability(self, capability: str) -> list[RegistryEntry[T]]:
        """Find all entries that declare the specified capability."""
        return [
            entry
            for entry in self._entries.values()
            if capability in entry.capabilities
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[str]:
        return iter(self.list())

    def __repr__(self) -> str:
        return f"<Registry {self.name!r} ({len(self._entries)} items)>"


# Global canonical registries for ExamForge
stages: Registry[Any] = Registry("stages")
validators: Registry[Any] = Registry("validators")
languages: Registry[Any] = Registry("languages")
ocr_engines: Registry[Any] = Registry("ocr_engines")
exporters: Registry[Any] = Registry("exporters")
profiles: Registry[Any] = Registry("profiles")
llm_providers: Registry[Any] = Registry("llm_providers")
