"""Tests for v1 to v2 document migrator and loader (Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

from examforge.ir.migrator import load_document, migrate_v1_to_v2
from examforge.ir.schema import (
    ExamDocument,
    Option,
    Question,
    QuestionKind,
    TextNode,
)


def test_migrate_v1_plain_dict():
    v1_dict = {
        "source_path": "sample_v1.pdf",
        "source_hash": "sha256_legacy",
        "metadata": {"exam_name": "JEE Advanced", "year": 2023},
        "pages": [{"page_number": 1, "width_px": 800, "height_px": 1200}],
        "questions": [
            {
                "id": "q_10",
                "number": 10,
                "kind": "mcqn",
                "stem_text_en": "Select all correct statements.",
                "stem_text_hi": "सभी सही कथन चुनिए।",
                "options": [
                    {
                        "label": "A",
                        "text_str_en": "Statement A",
                        "text_str_hi": "कथन A",
                    },
                    {
                        "label": "B",
                        "text_str_en": "Statement B",
                        "text_str_hi": "कथन B",
                    },
                ],
            }
        ],
    }

    doc = migrate_v1_to_v2(v1_dict)
    assert doc.schema_version == 2
    assert len(doc.questions) == 1
    q = doc.questions[0]
    assert q.kind == QuestionKind.MULTI_CORRECT
    assert len(q.stem) >= 1
    assert isinstance(q.stem[0], TextNode)
    assert q.stem[0].texts["en"] == "Select all correct statements."
    assert q.stem[0].texts["hi"] == "सभी सही कथन चुनिए।"
    assert len(q.options) == 2
    assert q.options[0].content[0].texts["en"] == "Statement A"


def test_load_document_from_file(tmp_path: Path):
    doc_path = tmp_path / "legacy_doc.json"
    data = {
        "schema_version": 1,
        "source_path": "legacy.pdf",
        "questions": [
            {
                "id": "q1",
                "number": 1,
                "stem_text_en": "Question from file",
            }
        ],
    }
    with open(doc_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    loaded = load_document(doc_path)
    assert loaded.schema_version == 2
    assert loaded.questions[0].stem_text_en == "Question from file"
    assert loaded.questions[0].stem[0].texts["en"] == "Question from file"


def test_migration_idempotence():
    doc = ExamDocument(
        source_path="idempotent.pdf",
        questions=[
            Question(
                id="q_1",
                number=1,
                stem=[TextNode(texts={"en": "Test stem"})],
                options=[Option(label="A", content=[TextNode(texts={"en": "Opt A"})])],
            )
        ],
    )
    first_pass = migrate_v1_to_v2(doc)
    second_pass = migrate_v1_to_v2(first_pass)
    assert first_pass.model_dump() == second_pass.model_dump()
