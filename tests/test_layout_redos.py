"""Tests for ReDoS guard and safe regex compilation (Phase 6)."""

from __future__ import annotations

import time
import pytest

from examforge.layout.redos import SafeRegex, compile_safe_regex, validate_pattern_safety


class TestReDoSGuard:
    def test_safe_pattern_compiles_and_matches(self):
        safe_pat = r"^\s*(\d{1,3})\s*[.):]"
        sr = compile_safe_regex(safe_pat)
        assert isinstance(sr, SafeRegex)
        assert sr.match("  42. What is energy?") is not None
        assert sr.match("No number") is None

    def test_detects_catastrophic_backtracking_pattern(self):
        # Nested repetition with overlap causes exponential backtracking
        dangerous_pat = r"(a+)+$"
        is_safe, reason = validate_pattern_safety(dangerous_pat)
        assert not is_safe
        assert "nested" in reason.lower() or "quantifier" in reason.lower()

    def test_detects_nested_wildcard_backtracking(self):
        dangerous_pat = r"(.*a)*$"
        is_safe, reason = validate_pattern_safety(dangerous_pat)
        assert not is_safe

    def test_100kb_adversarial_string_under_50ms(self):
        # 100 KB string of repetitive characters
        adversarial_text = "a" * 100_000 + "!"
        
        core_patterns = [
            r"^\s*(\d{1,3})\s*[.):]",
            r"^\s*Q\.?\s*(\d{1,3})\s*[.):]?",
            r"^\s*\((\d{1,3})\)\s*",
            r"(?:^|\n)\s*\(([A-Da-d1-4])\)\s*",
            r"(?:PART\s*[-–:]?\s*[0-9IVX]+|SECTION\s*[-–:]?\s*[A-Za-z0-9()]+|PHYSICS|CHEMISTRY)",
            r"(?:Statement|Equation|Reaction|Case|Condition|Step|Figure|Fig|Part)\s*[-–:]?\s*$",
            r"(?:Read\s+the\s+(?:following\s+)?passage|Questions?\s+\d+\s*(?:to|-|–)\s*\d+)",
        ]

        for pat in core_patterns:
            sr = compile_safe_regex(pat)
            start = time.perf_counter()
            _ = sr.search(adversarial_text)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            assert elapsed_ms < 50.0, f"Pattern {pat} took {elapsed_ms:.2f}ms on 100KB input (limit: 50ms)"

    def test_safe_regex_timeout_on_adversarial_input(self):
        # If an unsafe pattern is forced through, safe search enforces timeout
        sr = SafeRegex(r"a*b", timeout_ms=30.0)
        start = time.perf_counter()
        _ = sr.search("a" * 50_000)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 100.0, f"Expected timeout under 100ms, took {elapsed_ms:.2f}ms"
