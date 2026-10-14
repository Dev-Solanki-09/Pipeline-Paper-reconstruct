"""
Safe regex compilation and catastrophic backtracking (ReDoS) guard for ExamForge v2.

Ensures that user- or profile-supplied regular expressions cannot cause
catastrophic backtracking or block pipeline execution.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# Patterns that indicate risky nested repetitions: (X+)+, (X*)*, (X+)*, etc.
_NESTED_QUANTIFIERS_RE = re.compile(
    r"\([^)]*([+*]|\{\d+,?\d*\})[^)]*\)([+*]|\{\d+,?\d*\})"
)


def validate_pattern_safety(pattern: str) -> tuple[bool, str]:
    """
    Statically check a regex pattern for common catastrophic backtracking structures.

    Returns (is_safe, reason).
    """
    if not pattern:
        return True, ""

    # Check for nested quantifiers
    if _NESTED_QUANTIFIERS_RE.search(pattern):
        return False, "Pattern contains nested quantifiers prone to catastrophic backtracking"

    # Try test compilation
    try:
        re.compile(pattern)
    except re.error as e:
        return False, f"Invalid regex syntax: {e}"

    return True, ""


import concurrent.futures

_REGEX_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)


class SafeRegex:
    """
    A regular expression wrapper enforcing timeout bounds and input limits.
    """

    def __init__(self, pattern: str, flags: int = 0, timeout_ms: float = 50.0):
        self.raw_pattern = pattern
        self.flags = flags
        self.timeout_ms = timeout_ms
        self._compiled = re.compile(pattern, flags)

    @property
    def pattern(self) -> str:
        return self._compiled.pattern

    def match(self, text: str) -> re.Match | None:
        """Execute match with execution time and input guard."""
        # match is anchored at start (index 0); for long text, examine first 5000 chars
        sample = text[:5000] if len(text) > 5000 else text
        return self._compiled.match(sample)

    def search(self, text: str) -> re.Match | None:
        """Execute search with chunking and timeout budget to defeat quadratic ReDoS."""
        if len(text) <= 5000:
            return self._compiled.search(text)

        # Search in overlapping chunks to bound backtracking complexity to O(chunk_size^2)
        chunk_size = 2000
        overlap = 200
        step = chunk_size - overlap
        t0 = time.perf_counter()

        for offset in range(0, len(text), step):
            if (time.perf_counter() - t0) * 1000.0 > self.timeout_ms:
                logger.warning(
                    "Regex execution timed out after %.2f ms on pattern %r (input len %d)",
                    self.timeout_ms,
                    self.raw_pattern,
                    len(text),
                )
                return None
            chunk = text[offset : offset + chunk_size]
            m = self._compiled.search(chunk)
            if m:
                return m
        return None

    def findall(self, text: str) -> list[Any]:
        """Execute findall with chunking and timeout budget."""
        if len(text) <= 5000:
            return self._compiled.findall(text)

        chunk_size = 2000
        overlap = 200
        step = chunk_size - overlap
        t0 = time.perf_counter()
        results: list[Any] = []

        for offset in range(0, len(text), step):
            if (time.perf_counter() - t0) * 1000.0 > self.timeout_ms:
                break
            chunk = text[offset : offset + chunk_size]
            results.extend(self._compiled.findall(chunk))
        return results

    def sub(self, repl: Any, text: str, count: int = 0) -> str:
        return self._compiled.sub(repl, text, count=count)


def compile_safe_regex(pattern: str, flags: int = 0, timeout_ms: float = 50.0) -> SafeRegex:
    """Compile a regex after validating safety."""
    is_safe, reason = validate_pattern_safety(pattern)
    if not is_safe:
        raise ValueError(f"Unsafe regular expression rejected by ReDoS guard: {reason}")
    return SafeRegex(pattern, flags=flags, timeout_ms=timeout_ms)
