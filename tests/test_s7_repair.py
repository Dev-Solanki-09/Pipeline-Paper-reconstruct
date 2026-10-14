"""Tests for Stage S7 Repair and escalation ladder."""

from __future__ import annotations

import json

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    Issue,
    IssueSeverity,
    Option,
    PageInfo,
    Question,
)
from examforge.llm.client import LLMClient
from examforge.llm.fake import FakeLLMClient
from examforge.stages.base import StageContext
from examforge.stages.s7_repair import S7Repair


def _make_test_doc_with_issue(severity: IssueSeverity = IssueSeverity.BLOCKER) -> ExamDocument:
    pages = [PageInfo(page_number=1, width_px=595, height_px=842)]
    stem_b = Block(
        id="b1", page=1, bbox=BBox(x1=10, y1=10, x2=200, y2=40), text="What is accleration?"
    )
    q = Question(
        id="q_1",
        number=1,
        stem_en=[stem_b],
        stem_text_en="What is accleration?",
        options=[
            Option(label="A", text_str_en="Rate of velocity change"),
            Option(label="B", text_str_en="Rate of position change"),
        ],
        source_pages=[1],
    )
    issue = Issue(
        id="r12_lexicon_q1",
        stage="s8_verify",
        rule="lexicon",
        severity=severity,
        message="Misspelled word accleration in Q1",
        evidence={"question_number": 1},
    )
    return ExamDocument(
        id="doc_repair",
        source_path="repair.pdf",
        pages=pages,
        blocks=[stem_b],
        questions=[q],
        issues=[issue],
    )


class TestS7RepairStage:
    def test_s7_repair_flag_off_rollback(self, tmp_path):
        doc = _make_test_doc_with_issue()
        config = ExamForgeConfig(flags={"s7_repair": False})
        ctx = StageContext(
            document=doc,
            spec=None,
            config=config,
            stage_dir=tmp_path / "s7",
            run_dir=tmp_path / "run",
        )

        stage = S7Repair()
        res = stage.run(ctx)
        assert res.metrics.get("s7_repair_skipped") is True
        # Issue preserved untouched
        assert len(res.issues) == 1
        assert doc.questions[0].stem_text_en == "What is accleration?"

    def test_s7_repair_t3_patch_success(self, tmp_path):
        doc = _make_test_doc_with_issue()
        config = ExamForgeConfig(flags={"s7_repair": True})

        fake_provider = FakeLLMClient()
        fake_provider.queue_response(
            json.dumps(
                {
                    "patches": [
                        {"op": "replace", "path": "/stem_text_en", "value": "What is acceleration?"}
                    ]
                }
            )
        )
        fake_client = LLMClient(provider=fake_provider)

        ctx = StageContext(
            document=doc,
            spec=None,
            config=config,
            stage_dir=tmp_path / "s7",
            run_dir=tmp_path / "run",
        )
        ctx.llm_client = fake_client

        stage = S7Repair()
        res = stage.run(ctx)

        assert res.metrics.get("repaired_count", 0) >= 1
        # Stem corrected
        assert doc.questions[0].stem_text_en == "What is acceleration?"
        # Issue resolved
        assert len(res.issues) == 0

    def test_s7_repair_hostile_injection_ignored(self, tmp_path):
        doc = _make_test_doc_with_issue()
        config = ExamForgeConfig(flags={"s7_repair": True})

        # Hostile patch attempting to overwrite immutable /id and /number
        fake_provider = FakeLLMClient()
        fake_provider.queue_response(
            json.dumps(
                {
                    "patches": [
                        {"op": "replace", "path": "/id", "value": "hacked_id"},
                        {"op": "replace", "path": "/number", "value": 999},
                    ]
                }
            )
        )
        fake_client = LLMClient(provider=fake_provider)

        ctx = StageContext(
            document=doc,
            spec=None,
            config=config,
            stage_dir=tmp_path / "s7",
            run_dir=tmp_path / "run",
        )
        ctx.llm_client = fake_client

        stage = S7Repair()
        res = stage.run(ctx)

        # Hostile patch rejected: id and number unchanged
        assert doc.questions[0].id == "q_1"
        assert doc.questions[0].number == 1
        # Escalated to T4 human review
        assert res.metrics.get("needs_review") is True

    def test_s7_repair_offline_mode_generates_review_html(self, tmp_path):
        doc = _make_test_doc_with_issue()
        config = ExamForgeConfig(flags={"s7_repair": True})

        ctx = StageContext(
            document=doc,
            spec=None,
            config=config,
            stage_dir=tmp_path / "s7",
            run_dir=tmp_path / "run",
        )
        # No remote LLM provider -> offline fallback to T4 review
        stage = S7Repair()
        res = stage.run(ctx)

        assert res.metrics.get("needs_review") is True
        assert res.metrics.get("exit_code") == 20
        # review.html generated
        review_file = tmp_path / "s7" / "review.html"
        assert review_file.exists()
        content = review_file.read_text(encoding="utf-8")
        assert "Human Review Required" in content
        assert "Misspelled word" in content
