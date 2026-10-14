"""
ExamForge v2: IR Schema Migrator & Loader.

Implements backward-compatibility migrator for v1 `document.json` artifacts,
ensuring pure, idempotent conversion into the universal v2 content model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from examforge.ir.schema import ExamDocument


def migrate_v1_to_v2(data: dict[str, Any] | ExamDocument) -> ExamDocument:
    """
    Migrate a v1 ExamDocument dictionary or object to v2.

    Pure and idempotent:
    migrate_v1_to_v2(migrate_v1_to_v2(doc)) == migrate_v1_to_v2(doc)
    """
    from examforge.ir.schema import (
        ExamDocument,
        Option,
        Question,
    )

    raw = data.model_dump() if isinstance(data, ExamDocument) else dict(data)

    # Ensure schema_version is 2
    raw["schema_version"] = 2

    # Process questions
    if "questions" in raw and isinstance(raw["questions"], list):
        migrated_questions: list[dict[str, Any]] = []
        for q_data in raw["questions"]:
            q_dict = q_data.model_dump() if isinstance(q_data, Question) else dict(q_data)

            # Synthesize stem ContentNodes if missing
            stem = q_dict.get("stem", [])
            if not stem:
                stem_en = q_dict.get("stem_text_en", "")
                stem_hi = q_dict.get("stem_text_hi", "")
                texts: dict[str, str] = {}
                if stem_en:
                    texts["en"] = stem_en
                if stem_hi:
                    texts["hi"] = stem_hi
                if texts:
                    stem = [{"kind": "text", "texts": texts}]
            q_dict["stem"] = stem

            # Synthesize option ContentNodes if missing
            options = q_dict.get("options", [])
            migrated_options: list[dict[str, Any]] = []
            for opt_data in options:
                opt_dict = opt_data.model_dump() if isinstance(opt_data, Option) else dict(opt_data)

                content = opt_dict.get("content", [])
                if not content:
                    opt_en = opt_dict.get("text_str_en", "")
                    opt_hi = opt_dict.get("text_str_hi", "")
                    opt_texts: dict[str, str] = {}
                    if opt_en:
                        opt_texts["en"] = opt_en
                    if opt_hi:
                        opt_texts["hi"] = opt_hi
                    if opt_texts:
                        content = [{"kind": "text", "texts": opt_texts}]
                opt_dict["content"] = content
                migrated_options.append(opt_dict)
            q_dict["options"] = migrated_options
            migrated_questions.append(q_dict)
        raw["questions"] = migrated_questions

    return ExamDocument.model_validate(raw)


def load_document(path: Path | str) -> ExamDocument:
    """
    Load an ExamDocument from JSON, transparently migrating v1 documents to v2.
    """
    file_path = Path(path)
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    return migrate_v1_to_v2(data)
