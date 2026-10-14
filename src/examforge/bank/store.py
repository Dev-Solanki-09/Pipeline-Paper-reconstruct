"""SQLite-backed Question Bank Store with schema versioning (Phase 12.1)."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1


def to_signed_64(val: int) -> int:
    """Convert unsigned 64-bit int to signed 64-bit for SQLite INTEGER compatibility."""
    return val if val < (1 << 63) else val - (1 << 64)


def to_unsigned_64(val: int) -> int:
    """Convert signed 64-bit int from SQLite INTEGER to unsigned 64-bit."""
    return val if val >= 0 else val + (1 << 64)


@dataclass
class BankQuestionRecord:
    """Represents a verified question entry stored in the question bank."""

    content_hash: str
    simhash: int
    number_signature: str
    languages: list[str]
    ir_json: str
    verified_by: str
    source_paper: str
    exam_family: str
    verified_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class QuestionBankStore:
    """Persistent SQLite question bank storage with migration management."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create and return an SQLite connection configured with WAL and timeout."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Initialize database tables and run pending migrations."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version;")
            ver = cursor.fetchone()[0]

            if ver == 0:
                self._migrate_to_v1(conn)
            elif ver < CURRENT_SCHEMA_VERSION:
                logger.info(
                    "Upgrading question bank from version %d to %d",
                    ver,
                    CURRENT_SCHEMA_VERSION,
                )

    def _migrate_to_v1(self, conn: sqlite3.Connection) -> None:
        """Initial schema migration: questions and figures tables."""
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                content_hash TEXT PRIMARY KEY,
                simhash INTEGER NOT NULL,
                number_signature TEXT NOT NULL,
                languages TEXT NOT NULL,
                ir_json TEXT NOT NULL,
                verified_by TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                source_paper TEXT NOT NULL,
                exam_family TEXT NOT NULL
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_q_simhash ON questions (simhash);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_q_family ON questions (exam_family);")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS figures (
                figure_hash TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
        conn.commit()

    def insert_question(self, record: BankQuestionRecord) -> None:
        """Insert or replace a question record."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO questions (
                    content_hash, simhash, number_signature, languages,
                    ir_json, verified_by, verified_at, source_paper, exam_family
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.content_hash,
                    to_signed_64(record.simhash),
                    record.number_signature,
                    json.dumps(record.languages),
                    record.ir_json,
                    record.verified_by,
                    record.verified_at,
                    record.source_paper,
                    record.exam_family,
                ),
            )
            conn.commit()

    def get_by_content_hash(self, content_hash: str) -> BankQuestionRecord | None:
        """Retrieve a record by exact content hash."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM questions WHERE content_hash = ?;",
                (content_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def find_candidates(
        self,
        exam_family: str | None = None,
        limit: int = 100,
    ) -> list[BankQuestionRecord]:
        """Query candidate questions, optionally filtered by exam family."""
        with self.get_connection() as conn:
            if exam_family:
                cursor = conn.execute(
                    "SELECT * FROM questions WHERE exam_family = ? LIMIT ?;",
                    (exam_family, limit),
                )
            else:
                cursor = conn.execute("SELECT * FROM questions LIMIT ?;", (limit,))
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def insert_figure(self, figure_hash: str, file_path: str) -> None:
        """Record a verified figure hash mapping."""
        with self.get_connection() as conn:
            now = datetime.now(UTC).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO figures (figure_hash, file_path, created_at)
                VALUES (?, ?, ?);
                """,
                (figure_hash, file_path, now),
            )
            conn.commit()

    def get_figure(self, figure_hash: str) -> str | None:
        """Lookup stored file path for a figure hash."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT file_path FROM figures WHERE figure_hash = ?;",
                (figure_hash,),
            )
            row = cursor.fetchone()
            return row["file_path"] if row else None

    def stats(self) -> dict[str, int]:
        """Return bank statistics."""
        with self.get_connection() as conn:
            q_cnt = conn.execute("SELECT COUNT(*) FROM questions;").fetchone()[0]
            f_cnt = conn.execute("SELECT COUNT(*) FROM figures;").fetchone()[0]
            return {"question_count": q_cnt, "figure_count": f_cnt}

    def purge(self) -> None:
        """Purge all question bank records."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM questions;")
            conn.execute("DELETE FROM figures;")
            conn.commit()

    def export_jsonl(self, file_path: Path | str) -> int:
        """Export all question records to a JSONL file. Returns record count."""
        out_path = Path(file_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with self.get_connection() as conn, out_path.open("w", encoding="utf-8") as f:
            cursor = conn.execute("SELECT * FROM questions ORDER BY content_hash;")
            for row in cursor:
                rec = self._row_to_record(row)
                data = {
                    "content_hash": rec.content_hash,
                    "simhash": rec.simhash,
                    "number_signature": rec.number_signature,
                    "languages": rec.languages,
                    "ir_json": rec.ir_json,
                    "verified_by": rec.verified_by,
                    "verified_at": rec.verified_at,
                    "source_paper": rec.source_paper,
                    "exam_family": rec.exam_family,
                }
                f.write(json.dumps(data) + "\n")
                count += 1
        return count

    def import_jsonl(self, file_path: Path | str) -> int:
        """Import question records from a JSONL file. Returns imported count."""
        in_path = Path(file_path)
        if not in_path.exists():
            return 0
        count = 0
        with in_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                rec = BankQuestionRecord(
                    content_hash=data["content_hash"],
                    simhash=data["simhash"],
                    number_signature=data["number_signature"],
                    languages=data["languages"],
                    ir_json=data["ir_json"],
                    verified_by=data.get("verified_by", "import"),
                    verified_at=data.get("verified_at", ""),
                    source_paper=data.get("source_paper", ""),
                    exam_family=data.get("exam_family", "unknown"),
                )
                self.insert_question(rec)
                count += 1
        return count

    def _row_to_record(self, row: sqlite3.Row) -> BankQuestionRecord:
        return BankQuestionRecord(
            content_hash=row["content_hash"],
            simhash=to_unsigned_64(row["simhash"]),
            number_signature=row["number_signature"],
            languages=json.loads(row["languages"]),
            ir_json=row["ir_json"],
            verified_by=row["verified_by"],
            verified_at=row["verified_at"],
            source_paper=row["source_paper"],
            exam_family=row["exam_family"],
        )
