"""
Phase 13.1 — Document Fingerprint Extraction and SQLite Cache.

Extracts layout gutters, header-band hashes, script mixes, numbering styles,
and option schemes from the first K pages of an exam paper, storing/retrieving
proposals in profile_cache.sqlite.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from examforge.ir.schema import ExamDocument, PageClassification


@dataclass
class DocumentFingerprint:
    """Consensus structural fingerprint of an exam document."""

    doc_hash: str
    page_count_sampled: int
    gutters: list[float] = field(default_factory=list)
    header_hash: str = ""
    script_distribution: dict[str, float] = field(default_factory=dict)
    dominant_numbering: str | None = None
    dominant_option_scheme: str | None = None
    estimated_columns: int = 1
    font_families: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _detect_char_script(ch: str) -> str | None:
    """Return Unicode script code for a character."""
    code = ord(ch)
    if (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
        return "Latn"
    if 0x0900 <= code <= 0x097F:
        return "Deva"
    if 0x0600 <= code <= 0x06FF:
        return "Arab"
    if 0x0B80 <= code <= 0x0BFF:
        return "Taml"
    if 0x0C00 <= code <= 0x0C7F:
        return "Telu"
    if 0x0A80 <= code <= 0x0AFF:
        return "Gujr"
    if 0x0B00 <= code <= 0x0B7F:
        return "Orya"
    if 0x0980 <= code <= 0x09FF:
        return "Beng"
    return None


_NUMBERING_PATTERNS = {
    "q_prefix": re.compile(r"(?im)^\s*Q\.?\s*\d+"),
    "dot": re.compile(r"(?im)^\s*\d{1,3}\s*\."),
    "paren": re.compile(r"(?im)^\s*\(\d{1,3}\)\s+[A-Za-z\u0900-\u097F]"),
    "hindi_prashna": re.compile(r"(?im)^\s*प्रश्न\s*\d+"),
}

_OPTION_PATTERNS = {
    "alpha_paren": re.compile(r"\([A-Da-d]\)"),
    "digit_paren": re.compile(r"\([1-4]\)"),
    "alpha_dot": re.compile(r"\b[A-Da-d]\."),
    "hindi_paren": re.compile(r"\([क-घ]\)"),
}


def extract_document_fingerprint(
    doc: ExamDocument,
    max_pages: int = 5,
) -> DocumentFingerprint:
    """
    Extract consensus structural fingerprint from first K content pages.
    """
    target_pages = (
        [p for p in doc.pages if p.classification in (PageClassification.QUESTIONS, None)]
        or doc.pages
    )[:max_pages]

    sampled_page_nums = {p.page_number for p in target_pages}
    page_w_map = {p.page_number: float(p.width_px or 600) for p in target_pages}
    page_h_map = {p.page_number: float(p.height_px or 800) for p in target_pages}

    sampled_blocks = [b for b in doc.blocks if b.page in sampled_page_nums]
    if not sampled_blocks and doc.source_path and Path(doc.source_path).exists():
        # O3.2 Cheap profiling input: sample text layer of target pages directly
        import pymupdf

        try:
            pdf = pymupdf.open(str(doc.source_path))
            for p_num in sampled_page_nums:
                p_idx = p_num - 1
                if 0 <= p_idx < len(pdf):
                    page = pdf[p_idx]
                    raw_blocks = page.get_text("blocks")
                    for b_idx, rb in enumerate(raw_blocks):
                        if len(rb) >= 5 and rb[4].strip():
                            from examforge.ir.schema import BBox, Block, BlockType

                            sampled_blocks.append(
                                Block(
                                    id=f"sample_{p_num}_{b_idx}",
                                    page=p_num,
                                    type=BlockType.TEXT,
                                    bbox=BBox(
                                        x1=int(rb[0]),
                                        y1=int(rb[1]),
                                        x2=int(rb[2]),
                                        y2=int(rb[3]),
                                    ),
                                    text=rb[4],
                                )
                            )
            pdf.close()
        except Exception:
            pass

    # 2. Script mix
    script_counts: dict[str, int] = {}
    total_script_chars = 0
    for b in sampled_blocks:
        for ch in b.text:
            s = _detect_char_script(ch)
            if s:
                script_counts[s] = script_counts.get(s, 0) + 1
                total_script_chars += 1

    script_dist: dict[str, float] = {}
    if total_script_chars > 0:
        for s, cnt in script_counts.items():
            script_dist[s] = round(cnt / total_script_chars, 4)

    # 3. Header band hash (blocks in top 12% of height)
    header_texts: list[str] = []
    for b in sampled_blocks:
        ph = page_h_map.get(b.page, 800.0)
        if b.bbox.y2 <= ph * 0.12 or b.bbox.y1 <= ph * 0.08:
            clean_t = re.sub(r"\s+", " ", b.text).strip()
            if clean_t:
                header_texts.append(clean_t)
    header_raw = " || ".join(sorted(set(header_texts)))
    header_hash = hashlib.sha256(header_raw.encode("utf-8")).hexdigest()[:16]

    # 4. Gutter and column estimation
    # Check horizontal overlap across blocks
    detected_gutters: list[float] = []
    estimated_columns = 1

    for p_num in sampled_page_nums:
        p_blocks = [
            b
            for b in sampled_blocks
            if b.page == p_num
            and (b.bbox.y2 > page_h_map.get(p_num, 800.0) * 0.12)  # exclude header
        ]
        if not p_blocks:
            continue
        pw = page_w_map.get(p_num, 600.0)
        # Check center region (e.g. 0.45*pw to 0.55*pw)
        mid_x1 = 0.45 * pw
        mid_x2 = 0.55 * pw

        left_blocks = [b for b in p_blocks if b.bbox.x2 <= mid_x2]
        right_blocks = [b for b in p_blocks if b.bbox.x1 >= mid_x1]
        spanning_blocks = [b for b in p_blocks if b.bbox.x1 < mid_x1 and b.bbox.x2 > mid_x2]

        if len(left_blocks) >= 2 and len(right_blocks) >= 2 and len(spanning_blocks) <= 1:
            # Gutter between max left x2 and min right x1
            max_left = max(b.bbox.x2 for b in left_blocks)
            min_right = min(b.bbox.x1 for b in right_blocks)
            gutter_center = (max_left + min_right) / 2.0
            detected_gutters.append(round(gutter_center, 1))

    if len(detected_gutters) >= max(1, len(sampled_page_nums) // 2):
        estimated_columns = 2

    # 5. Numbering and Option signals
    all_text = "\n".join(b.text for b in sampled_blocks)

    num_counts = {name: len(pat.findall(all_text)) for name, pat in _NUMBERING_PATTERNS.items()}
    best_num = max(num_counts.items(), key=lambda kv: kv[1]) if num_counts else (None, 0)
    dominant_numbering = best_num[0] if best_num[1] > 0 else None

    opt_counts = {name: len(pat.findall(all_text)) for name, pat in _OPTION_PATTERNS.items()}
    best_opt = max(opt_counts.items(), key=lambda kv: kv[1]) if opt_counts else (None, 0)
    dominant_option = best_opt[0] if best_opt[1] > 0 else None

    # 6. Synthesize doc_hash
    components = [
        f"cols:{estimated_columns}",
        f"scripts:{sorted(script_dist.items())}",
        f"num:{dominant_numbering}",
        f"opt:{dominant_option}",
        f"hdr:{header_hash}",
    ]
    doc_hash = hashlib.sha256(";".join(components).encode("utf-8")).hexdigest()[:32]

    return DocumentFingerprint(
        doc_hash=doc_hash,
        page_count_sampled=len(sampled_page_nums),
        gutters=sorted(set(detected_gutters)),
        header_hash=header_hash,
        script_distribution=script_dist,
        dominant_numbering=dominant_numbering,
        dominant_option_scheme=dominant_option,
        estimated_columns=estimated_columns,
    )


class ProfileCache:
    """Persistent SQLite cache mapping document fingerprints to learned/scaffolded profiles."""

    def __init__(self, db_path: Path | str = Path("data/profiles/profile_cache.sqlite")) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_cache (
                    fingerprint_hash TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    profile_yaml TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def lookup(self, fingerprint_hash: str) -> tuple[str, str, float, int] | None:
        """Lookup stored profile proposal: (profile_id, profile_yaml, confidence, hit_count)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT profile_id, profile_yaml, confidence, hit_count
                FROM profile_cache
                WHERE fingerprint_hash = ?;
                """,
                (fingerprint_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return (
                row["profile_id"],
                row["profile_yaml"],
                float(row["confidence"]),
                int(row["hit_count"]),
            )

    def store(
        self,
        fingerprint_hash: str,
        profile_id: str,
        profile_yaml: str,
        confidence: float,
    ) -> None:
        """Store or update a profile proposal in the cache."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO profile_cache (
                    fingerprint_hash, profile_id, profile_yaml,
                    confidence, hit_count, created_at, last_used_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(fingerprint_hash) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    profile_yaml = excluded.profile_yaml,
                    confidence = excluded.confidence,
                    last_used_at = excluded.last_used_at;
                """,
                (fingerprint_hash, profile_id, profile_yaml, confidence, now, now),
            )
            conn.commit()

    def record_hit(self, fingerprint_hash: str) -> None:
        """Increment hit count and update last_used_at timestamp."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE profile_cache
                SET hit_count = hit_count + 1,
                    last_used_at = ?
                WHERE fingerprint_hash = ?;
                """,
                (now, fingerprint_hash),
            )
            conn.commit()

    def purge(self) -> None:
        """Purge all entries from profile cache."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM profile_cache;")
            conn.commit()
