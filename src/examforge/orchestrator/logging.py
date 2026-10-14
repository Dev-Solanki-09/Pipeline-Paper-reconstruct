"""
Phase 16.8 — Structured JSON Logging with Secret Redaction.

Outputs structured JSON log records with run_id, stage, and ISO timestamps.
Automatically redacts sensitive keys, auth tokens, and API credentials.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

# Patterns identifying secrets to redact
SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[:=]\s*['\"]?)[a-zA-Z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(token\s*[:=]\s*['\"]?)[a-zA-Z0-9_\-\.]{8,}", re.IGNORECASE),
    re.compile(r"(password\s*[:=]\s*['\"]?)[^\s'\"]+", re.IGNORECASE),
    re.compile(r"(sk-[a-zA-Z0-9]{16,})", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Mask secrets and API keys within log strings."""
    redacted = text
    for pat in SECRET_PATTERNS:
        redacted = pat.sub(r"\1***REDACTED***", redacted)
    return redacted


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON lines."""

    def __init__(self, run_id: str = "default", stage: str = "pipeline") -> None:
        super().__init__()
        self.run_id = run_id
        self.stage = stage

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        clean_msg = redact_secrets(msg)

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", self.run_id),
            "stage": getattr(record, "stage", self.stage),
            "message": clean_msg,
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_run_logging(
    run_id: str,
    log_file: str | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configures structured JSON logging for a pipeline execution."""
    root_logger = logging.getLogger("examforge")
    root_logger.setLevel(level)

    formatter = StructuredJsonFormatter(run_id=run_id)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        fh.setLevel(level)
        root_logger.addHandler(fh)

    return root_logger
