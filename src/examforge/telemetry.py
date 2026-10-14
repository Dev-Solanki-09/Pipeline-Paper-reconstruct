"""
ExamForge v2: Telemetry Ledger.

Tracks per-stage execution time, peak RSS memory consumption across platforms
(Windows / Linux / macOS), LLM token consumption, cost estimates, and escalation tiers.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def get_peak_rss_bytes() -> int:
    """
    Return peak resident set size (RSS) in bytes for the current process.

    Uses standard library ctypes on Windows and resource on POSIX systems.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            func = getattr(
                ctypes.windll.kernel32,
                "K32GetProcessMemoryInfo",
                getattr(ctypes.windll.psapi, "GetProcessMemoryInfo", None),
            )
            if func is not None:
                func.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
                    wintypes.DWORD,
                ]
                func.restype = wintypes.BOOL
                if func(handle, ctypes.byref(counters), counters.cb):
                    return int(counters.PeakWorkingSetSize)
        except Exception:
            return 0
        return 0
    else:
        try:
            import resource

            rusage = resource.getrusage(resource.RUSAGE_SELF)
            if sys.platform == "darwin":
                return int(rusage.ru_maxrss)
            return int(rusage.ru_maxrss * 1024)
        except Exception:
            return 0


@dataclass
class StageTelemetry:
    """Telemetry recorded for a single pipeline stage."""

    stage_name: str
    duration_seconds: float = 0.0
    peak_rss_bytes: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    call_count: int = 0
    escalation_tier: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelemetryLedger:
    """
    Central run telemetry ledger.

    Records stage runtimes, system resource usage, LLM token expenditures,
    and escalation distribution across repair tiers.
    """

    run_id: str
    stages: list[StageTelemetry] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    peak_rss_bytes: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    questions_touched_by_llm: list[int] = field(default_factory=list)
    escalation_counts: dict[str, int] = field(default_factory=dict)
    _active_stage: StageTelemetry | None = field(default=None, init=False, repr=False)

    @contextlib.contextmanager
    def track_stage(self, stage_name: str) -> Iterator[StageTelemetry]:
        """Context manager to measure runtime and RSS memory of a pipeline stage."""
        stage = StageTelemetry(stage_name=stage_name)
        self._active_stage = stage
        start_time = time.perf_counter()
        try:
            yield stage
        finally:
            elapsed = time.perf_counter() - start_time
            stage.duration_seconds = elapsed
            stage.peak_rss_bytes = get_peak_rss_bytes()
            if stage.peak_rss_bytes > self.peak_rss_bytes:
                self.peak_rss_bytes = stage.peak_rss_bytes
            self.total_duration_seconds += elapsed
            self.stages.append(stage)
            self._active_stage = None

    def record_llm_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float = 0.0,
        question_no: int | None = None,
        stage_name: str | None = None,
    ) -> None:
        """Record tokens and cost spent on an LLM invocation."""
        tot = prompt_tokens + completion_tokens
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += tot
        self.total_cost_usd += cost_usd

        target_stage = self._active_stage
        if stage_name:
            for s in self.stages:
                if s.stage_name == stage_name:
                    target_stage = s
                    break

        if target_stage is not None:
            target_stage.prompt_tokens += prompt_tokens
            target_stage.completion_tokens += completion_tokens
            target_stage.total_tokens += tot
            target_stage.cost_usd += cost_usd
            target_stage.call_count += 1

        if question_no is not None and question_no not in self.questions_touched_by_llm:
            self.questions_touched_by_llm.append(question_no)
            self.questions_touched_by_llm.sort()

    def record_escalation(self, tier: str, question_no: int | None = None) -> None:
        """Record escalation tier (T0_RULE, T1_LOCAL, T2_MCQ_VLM, T3_PATCH, T4_HUMAN)."""
        self.escalation_counts[tier] = self.escalation_counts.get(tier, 0) + 1
        if self._active_stage is not None:
            self._active_stage.escalation_tier = tier

    def get_escalation_rate(self) -> int:
        """Total number of escalations recorded."""
        return sum(self.escalation_counts.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert ledger to a deterministic serializable dictionary."""
        return {
            "run_id": self.run_id,
            "total_duration_seconds": round(self.total_duration_seconds, 4),
            "peak_rss_bytes": self.peak_rss_bytes,
            "peak_rss_mb": round(self.peak_rss_bytes / (1024 * 1024), 2),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "questions_touched_by_llm": sorted(self.questions_touched_by_llm),
            "escalation_counts": dict(sorted(self.escalation_counts.items())),
            "stages": [asdict(s) for s in self.stages],
        }

    def save_json(self, path: Path) -> None:
        """Save telemetry ledger to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    @classmethod
    def load_json(cls, path: Path) -> TelemetryLedger:
        """Load telemetry ledger from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        stages = [StageTelemetry(**s) for s in data.get("stages", [])]
        ledger = cls(
            run_id=data["run_id"],
            stages=stages,
            total_duration_seconds=data.get("total_duration_seconds", 0.0),
            peak_rss_bytes=data.get("peak_rss_bytes", 0),
            total_prompt_tokens=data.get("total_prompt_tokens", 0),
            total_completion_tokens=data.get("total_completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            questions_touched_by_llm=data.get("questions_touched_by_llm", []),
            escalation_counts=data.get("escalation_counts", {}),
        )
        return ledger
