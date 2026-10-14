"""
Phase 16.2 — Hardened Atomic I/O, Run Directory Management, and Lockfiles.

Provides:
- Write-temp + fsync + replace for crash-proof atomic updates.
- Exclusive run directory lockfile (run.lock) with cross-platform support.
- Run ID sanitization (path traversal protection).
- Versioned run ID generator: <UTC-ts>_<paper-hash8>_<n>.
- Append-only events.jsonl with derived summary.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def sanitize_run_id(run_id: str) -> str:
    """
    Sanitize run_id to strictly prevent directory traversal (e.g. '../../etc').
    Replaces illegal path characters with underscores.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", run_id).strip("_")
    if not cleaned or cleaned.startswith("."):
        return f"run_{secrets.token_hex(4)}"
    return cleaned


def generate_run_id(paper_hash: str = "", sequence_num: int = 1) -> str:
    """
    Format: <UTC-date>_<UTC-time>_<hash_or_hex>
    Ensures exactly 3 underscore-delimited parts (date, time, hex/hash)
    for compatibility and versioned run directories.
    """
    dt = datetime.now(UTC)
    date_str = dt.strftime("%Y%m%d")
    time_str = dt.strftime("%H%M%S")
    if paper_hash:
        h8 = re.sub(r"[^a-fA-F0-9]", "", paper_hash)[:8]
        if len(h8) < 8:
            h8 = h8.ljust(8, "0")
        suffix = f"{h8[:6]}{sequence_num}"
    else:
        suffix = secrets.token_hex(3)
    return f"{date_str}_{time_str}_{suffix}"


def atomic_write(path: Path | str, content: str | bytes) -> None:
    """
    Write content to file atomically via temporary file, fsync, and rename.
    Guarantees no half-written or corrupted state if interrupted mid-write.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp_suffix = f".tmp.{secrets.token_hex(4)}"
    tmp_path = p.with_name(f"{p.name}{temp_suffix}")

    is_bytes = isinstance(content, bytes)
    mode = "wb" if is_bytes else "w"
    encoding = None if is_bytes else "utf-8"

    try:
        with open(tmp_path, mode, encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(p)
    except Exception:
        with contextlib.suppress(Exception):
            tmp_path.unlink(missing_ok=True)
        raise


class RunLockError(RuntimeError):
    """Raised when an active run lock cannot be acquired."""


class RunLock:
    """
    Exclusive lockfile (run.lock) preventing concurrent executions
    in the same run directory.
    """

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)
        self.lock_path = self.run_dir / "run.lock"
        self._acquired = False

    def acquire(self, timeout_sec: float = 2.0) -> None:
        import time

        start = time.time()
        self.run_dir.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                # Exclusive file creation
                fd = self.lock_path.open("x")
                lock_info = {
                    "pid": os.getpid(),
                    "time": datetime.now(UTC).isoformat(),
                }
                fd.write(json.dumps(lock_info))
                fd.flush()
                fd.close()
                self._acquired = True
                return
            except FileExistsError as err:
                # Check for stale lock (> 60 seconds)
                try:
                    if self.lock_path.exists():
                        mtime = self.lock_path.stat().st_mtime
                        if time.time() - mtime > 60.0:
                            logger.warning("Breaking stale lock %s", self.lock_path)
                            self.lock_path.unlink(missing_ok=True)
                            continue
                except Exception:
                    pass

                if time.time() - start >= timeout_sec:
                    raise RunLockError(
                        f"Another process holds the lock for run directory {self.run_dir}"
                    ) from err
                time.sleep(0.05)

    def release(self) -> None:
        if self._acquired and self.lock_path.exists():
            with contextlib.suppress(Exception):
                self.lock_path.unlink(missing_ok=True)
            self._acquired = False

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


class EventLogger:
    """
    Append-only events.jsonl recorder for operational tracing
    with on-the-fly summary derivation.
    """

    def __init__(self, run_dir: Path | str) -> None:
        self.events_path = Path(run_dir) / "events.jsonl"
        self.events_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: str, stage: str, data: dict[str, Any] | None = None) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "stage": stage,
            "data": data or {},
        }
        raw = json.dumps(event) + "\n"
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(raw)
            f.flush()

    def get_summary(self) -> dict[str, Any]:
        """Derive stage status and event counts from append-only events.jsonl."""
        if not self.events_path.exists():
            return {"total_events": 0, "stages_completed": []}

        total = 0
        stages_started: set[str] = set()
        stages_completed: list[str] = []
        errors: list[str] = []

        with open(self.events_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    ev = json.loads(line)
                    ev_type = ev.get("event_type")
                    stage = ev.get("stage")
                    if ev_type == "stage_start":
                        stages_started.add(stage)
                    elif ev_type == "stage_complete":
                        if stage not in stages_completed:
                            stages_completed.append(stage)
                    elif ev_type == "stage_error":
                        err_msg = ev.get("data", {}).get("error", "unknown error")
                        errors.append(f"{stage}: {err_msg}")
                except Exception:
                    continue

        return {
            "total_events": total,
            "stages_completed": stages_completed,
            "errors": errors,
        }
