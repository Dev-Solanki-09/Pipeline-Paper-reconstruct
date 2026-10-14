"""Document ingestion into verified Question Bank (Phase 12.4)."""

from __future__ import annotations

import hashlib
import json
import logging

from examforge.bank.fingerprint import (
    compute_number_signature,
    compute_simhash_64,
    normalize_text_for_fingerprint,
)
from examforge.bank.store import BankQuestionRecord, QuestionBankStore
from examforge.ir.schema import ExamDocument, Question

logger = logging.getLogger(__name__)


def compute_question_content_hash(question: Question) -> str:
    """Compute a deterministic SHA-256 content hash for a question."""
    parts = []
    if question.stem_text_en:
        parts.append(normalize_text_for_fingerprint(question.stem_text_en))
    if question.stem_text_hi:
        parts.append(normalize_text_for_fingerprint(question.stem_text_hi))

    for opt in question.options:
        parts.append(f"[{opt.label}]")
        if opt.text_str_en:
            parts.append(normalize_text_for_fingerprint(opt.text_str_en))
        if opt.text_str_hi:
            parts.append(normalize_text_for_fingerprint(opt.text_str_hi))

    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def ingest_document(
    store: QuestionBankStore,
    doc: ExamDocument,
    verified_by: str,
    exam_family: str,
) -> int:
    """
    Ingest all questions from an approved ExamDocument into the Question Bank.

    Returns the count of questions successfully ingested.
    """
    count = 0
    source_name = str(doc.source_path or "unknown_source")

    for q in doc.questions:
        c_hash = compute_question_content_hash(q)
        stem_txt = q.stem_text_en or q.stem_text_hi or ""
        sh = compute_simhash_64(stem_txt)
        sig = compute_number_signature(q)

        languages = []
        if q.stem_text_en:
            languages.append("en")
        if q.stem_text_hi:
            languages.append("hi")

        q_json = json.dumps(q.model_dump(mode="json"))

        rec = BankQuestionRecord(
            content_hash=c_hash,
            simhash=sh,
            number_signature=sig,
            languages=languages,
            ir_json=q_json,
            verified_by=verified_by,
            source_paper=source_name,
            exam_family=exam_family,
        )
        store.insert_question(rec)
        count += 1

    logger.info("Ingested %d question(s) from %s into QuestionBank", count, source_name)
    return count
