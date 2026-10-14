"""Tests for Question Bank reuse path in S4 structure (Phase 12.5)."""

from __future__ import annotations

from pathlib import Path

from examforge.bank.ingest import ingest_document
from examforge.bank.store import QuestionBankStore
from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    Option,
    PageClassification,
    PageInfo,
    Provenance,
    Question,
)
from examforge.stages.base import StageContext
from examforge.stages.s4_structure import S4Structure


def test_bank_reuse_disabled_by_default(tmp_path: Path):
    stage = S4Structure()
    cfg = ExamForgeConfig()

    doc = ExamDocument(
        source_path="test.pdf",
        pages=[
            PageInfo(
                page_number=1,
                width_px=595,
                height_px=842,
                classification=PageClassification.QUESTIONS,
            )
        ],
        blocks=[
            Block(
                id="b1",
                page=1,
                bbox=BBox(x1=10, y1=10, x2=200, y2=30),
                text="1. Calculate kinetic energy.",
            ),
            Block(id="b2", page=1, bbox=BBox(x1=10, y1=35, x2=200, y2=50), text="(A) 10 J"),
            Block(id="b3", page=1, bbox=BBox(x1=10, y1=55, x2=200, y2=70), text="(B) 20 J"),
        ],
    )

    ctx = StageContext(
        document=doc,
        spec=None,
        config=cfg,
        stage_dir=tmp_path / "s4",
        run_dir=tmp_path / "run",
    )

    res = stage.run(ctx)
    assert len(res.document.questions) == 1
    # By default, bank is disabled, so provenance is EXTRACTED
    assert res.document.questions[0].provenance == Provenance.EXTRACTED


def test_bank_reuse_enabled_with_match(tmp_path: Path):
    bank_db = tmp_path / "bank.db"
    store = QuestionBankStore(bank_db)

    # Ingest verified question into bank
    verified_doc = ExamDocument(
        source_path="verified_past_paper.pdf",
        pages=[PageInfo(page_number=1, width_px=595, height_px=842)],
        questions=[
            Question(
                id="q1",
                number=1,
                stem_text_en="Calculate kinetic energy.",
                options=[
                    Option(label="A", text_str_en="10 J"),
                    Option(label="B", text_str_en="20 J"),
                ],
            )
        ],
    )
    ingest_document(store, verified_doc, verified_by="senior_examiner", exam_family="neet_ug")

    # Now run S4 with bank enabled
    stage = S4Structure()
    cfg = ExamForgeConfig()
    cfg.flags["bank"] = True
    cfg.bank_path = bank_db

    doc = ExamDocument(
        source_path="new_paper.pdf",
        pages=[
            PageInfo(
                page_number=1,
                width_px=595,
                height_px=842,
                classification=PageClassification.QUESTIONS,
            )
        ],
        blocks=[
            Block(
                id="b1",
                page=1,
                bbox=BBox(x1=10, y1=10, x2=200, y2=30),
                text="1. Calculate kinetic energy.",
            ),
            Block(id="b2", page=1, bbox=BBox(x1=10, y1=35, x2=200, y2=50), text="(A) 10 J"),
            Block(id="b3", page=1, bbox=BBox(x1=10, y1=55, x2=200, y2=70), text="(B) 20 J"),
        ],
    )

    ctx = StageContext(
        document=doc,
        spec=None,
        config=cfg,
        stage_dir=tmp_path / "s4",
        run_dir=tmp_path / "run",
    )

    res = stage.run(ctx)
    assert len(res.document.questions) == 1
    reused_q = res.document.questions[0]
    assert reused_q.provenance == Provenance.BANK
    assert reused_q.confidence == 1.0
