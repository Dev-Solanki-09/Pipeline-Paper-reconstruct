"""
Tests for Phase O5: Repair Safety and Token Guardrails.

Verifies:
- O5.1: Net-benefit ledger records validators before/after, accepted/reverted status,
        and auto-disables tiers with zero or negative net benefit.
- O5.2: LLM-eligible issues only: BLOCKER severity AND localized bounds AND candidates/text.
        WARN issues and low-evidence issues never reach T2/T3. Per-paper issue cap enforced.
- O5.3: Preference for local tiers (T0/T1) before model escalation.
- O5.4: Per-paper token budget in profile/config halts repairs and exits with code 20.
- O5.5: Oracle vs Adversarial FakeLLM: patch guards reject forbidden paths, digit changes,
        and new blockers; repair harm rate <= 0.1%; WARN-only issues produce 0 model calls.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    ExamMetadata,
    Issue,
    IssueSeverity,
    Option,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.llm.client import LLMClient
from examforge.llm.fake import FakeLLMClient
from examforge.repair.ledger import NetBenefitLedger, RepairAttemptRecord
from examforge.repair.patch import UnsafePatchError, apply_patch_to_question
from examforge.repair.router import RepairRouter, RepairTier, is_llm_eligible
from examforge.stages.base import StageContext
from examforge.stages.s7_repair import S7Repair


def _create_test_question(q_id: str = "q1", number: int = 1, stem_text: str = "Find accleration.") -> Question:
    return Question(
        id=q_id,
        number=number,
        kind=QuestionKind.SINGLE_CORRECT,
        stem_text_en=stem_text,
        options=[
            Option(label="A", text_str_en="10 m/s^2"),
            Option(label="B", text_str_en="20 m/s^2"),
        ],
        source_pages=[1],
    )


def test_o5_1_net_benefit_ledger_and_auto_disable(tmp_path: Path):
    """Verify NetBenefitLedger records attempts and auto-disables non-beneficial tiers."""
    ledger = NetBenefitLedger(run_dir=tmp_path)

    # 1. Beneficial attempt (blockers before: 2, after: 1 -> net: +1)
    rec1 = RepairAttemptRecord(
        paper_id="paper_1",
        question_id="q1",
        rule="lexicon",
        tier="T3",
        blockers_before=2,
        blockers_after=1,
        net_benefit=1,
        status="accepted",
    )
    ledger.record_attempt(rec1)
    assert not ledger.is_tier_disabled("lexicon", "T3")

    # 2. Harmful attempts (blockers before: 1, after: 2 -> net: -1)
    rec2 = RepairAttemptRecord(
        paper_id="paper_1",
        question_id="q1",
        rule="formulas",
        tier="T3",
        blockers_before=1,
        blockers_after=2,
        net_benefit=-1,
        status="reverted",
        revert_reason="Patch introduced new blocker",
    )
    rec3 = RepairAttemptRecord(
        paper_id="paper_1",
        question_id="q1",
        rule="formulas",
        tier="T3",
        blockers_before=1,
        blockers_after=1,
        net_benefit=0,
        status="reverted",
        revert_reason="Target issue not resolved",
    )
    ledger.record_attempt(rec2)
    ledger.record_attempt(rec3)

    # formulas on T3 has cumulative benefit -1 <= 0 after 2 attempts -> auto-disabled
    assert ledger.is_tier_disabled("formulas", "T3", min_attempts=2)

    # Router skips disabled tier
    router = RepairRouter()
    issue = Issue(
        id="i_f",
        stage="s8_verify",
        rule="formulas",
        severity=IssueSeverity.BLOCKER,
        message="Formula syntax error",
        evidence={"question_number": 1},
    )
    disabled = {RepairTier.T3}
    # Ladder for formulas is T1, T3, T4. With T3 disabled, attempt 1 routes to T4
    tier = router.route(issue, attempt=1, disabled_tiers=disabled)
    assert tier == RepairTier.T4

    # File export verification
    assert (tmp_path / "repair_ledger.jsonl").exists()
    lines = (tmp_path / "repair_ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_o5_2_llm_eligibility_and_per_paper_cap(tmp_path: Path):
    """Verify is_llm_eligible checks and per-paper repair cap enforcement."""
    q = _create_test_question()

    # Case 1: WARN severity is ineligible
    warn_issue = Issue(
        id="warn_1",
        stage="s8_verify",
        rule="lexicon",
        severity=IssueSeverity.WARNING,
        message="Warning issue",
    )
    eligible, reason = is_llm_eligible(warn_issue, q)
    assert not eligible
    assert "not BLOCKER" in reason

    # Case 2: No localized bounds is ineligible
    q_no_pages = q.model_copy(update={"source_pages": []})
    no_loc_issue = Issue(
        id="no_loc",
        stage="s8_verify",
        rule="lexicon",
        severity=IssueSeverity.BLOCKER,
        message="Blocker with no location",
        evidence={},
    )
    eligible, reason = is_llm_eligible(no_loc_issue, q_no_pages)
    assert not eligible
    assert "No localized" in reason

    # Case 3: Valid blocker with question source_pages is eligible
    valid_issue = Issue(
        id="valid_1",
        stage="s8_verify",
        rule="lexicon",
        severity=IssueSeverity.BLOCKER,
        message="Valid blocker",
        evidence={"question_number": 1},
    )
    eligible, reason = is_llm_eligible(valid_issue, q)
    assert eligible

    # Case 4: Per-paper cap in S7Repair
    doc = ExamDocument(
        schema_version=2,
        source_path="test.pdf",
        metadata=ExamMetadata(exam_name="Cap Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700)],
        questions=[
            _create_test_question("q1", 1, "accleration 1"),
            _create_test_question("q2", 2, "accleration 2"),
            _create_test_question("q3", 3, "accleration 3"),
        ],
        issues=[
            Issue(id="i1", stage="s8_verify", rule="lexicon", severity=IssueSeverity.BLOCKER, message="Typo 1", evidence={"question_number": 1}),
            Issue(id="i2", stage="s8_verify", rule="lexicon", severity=IssueSeverity.BLOCKER, message="Typo 2", evidence={"question_number": 2}),
            Issue(id="i3", stage="s8_verify", rule="lexicon", severity=IssueSeverity.BLOCKER, message="Typo 3", evidence={"question_number": 3}),
        ],
    )

    fake_provider = FakeLLMClient(default_content=json.dumps({"patches": [
        {"op": "replace", "path": "/stem_text_en", "value": "acceleration"}
    ]}))
    fake_client = LLMClient(provider=fake_provider)

    # Config with max_llm_repairs = 2
    class CapConfig(ExamForgeConfig):
        max_llm_repairs: int = 2

    ctx = StageContext(
        document=doc,
        spec=None,
        config=CapConfig(flags={"s7_repair": True}),
        stage_dir=tmp_path / "s7",
        run_dir=tmp_path / "run",
    )
    ctx.llm_client = fake_client

    stage = S7Repair()
    res = stage.run(ctx)

    # Only 2 repairs were performed via LLM, 3rd was capped
    assert res.metrics["llm_repairs_count"] <= 2
    assert len(fake_provider.calls) <= 2
    assert res.metrics.get("needs_review") is True


def test_o5_3_prefer_local_tiers():
    """Verify local deterministic tiers (T0) resolve sequence gaps with 0 model calls."""
    doc = ExamDocument(
        schema_version=2,
        source_path="test.pdf",
        metadata=ExamMetadata(exam_name="T0 Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700)],
        blocks=[
            Block(id="b_gap", page=1, bbox=BBox(x1=10, y1=100, x2=200, y2=150), text="2. Recovered question text.\n(A) Opt 1\n(B) Opt 2")
        ],
        questions=[
            _create_test_question("q1", 1, "Question 1"),
            _create_test_question("q3", 3, "Question 3"),
        ],
        issues=[
            Issue(
                id="r14_gap_q2",
                stage="s8_verify",
                rule="sequence_gaps",
                severity=IssueSeverity.BLOCKER,
                message="Missing question 2",
                evidence={"missing_questions": [2], "page_neighborhood": [1, 1]},
            )
        ],
    )

    fake_provider = FakeLLMClient()
    fake_client = LLMClient(provider=fake_provider)

    ctx = StageContext(
        document=doc,
        spec=None,
        config=ExamForgeConfig(flags={"s7_repair": True}),
        stage_dir=Path("./tmp_s7"),
        run_dir=Path("./tmp_run"),
    )
    ctx.llm_client = fake_client

    stage = S7Repair()
    res = stage.run(ctx)

    # Solved deterministically via T0 gap search
    assert res.metrics["repaired_count"] == 1
    assert len(fake_provider.calls) == 0
    assert any(q.number == 2 for q in res.document.questions)


def test_o5_4_per_paper_token_budget_enforcement(tmp_path: Path):
    """Verify token budget exhaustion halts repairs and sets exit code 20."""
    doc = ExamDocument(
        schema_version=2,
        source_path="test.pdf",
        metadata=ExamMetadata(exam_name="Budget Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700)],
        questions=[
            _create_test_question("q1", 1, "accleration 1"),
            _create_test_question("q2", 2, "accleration 2"),
        ],
        issues=[
            Issue(id="i1", stage="s8_verify", rule="lexicon", severity=IssueSeverity.BLOCKER, message="Typo 1", evidence={"question_number": 1}),
            Issue(id="i2", stage="s8_verify", rule="lexicon", severity=IssueSeverity.BLOCKER, message="Typo 2", evidence={"question_number": 2}),
        ],
    )

    fake_provider = FakeLLMClient(default_content=json.dumps({"patches": [
        {"op": "replace", "path": "/stem_text_en", "value": "acceleration"}
    ]}))
    fake_client = LLMClient(provider=fake_provider)

    # Config with token_budget = 40 (less than 1 attempt's ~50 tokens)
    class BudgetConfig(ExamForgeConfig):
        token_budget: int = 40

    ctx = StageContext(
        document=doc,
        spec=None,
        config=BudgetConfig(flags={"s7_repair": True}),
        stage_dir=tmp_path / "s7",
        run_dir=tmp_path / "run",
    )
    ctx.llm_client = fake_client

    stage = S7Repair()
    res = stage.run(ctx)

    # Token budget was exhausted after 1 call
    assert res.metrics["budget_exhausted"] is True
    assert res.metrics["exit_code"] == 20
    assert res.metrics["needs_review"] is True
    assert (tmp_path / "run" / "review.html").exists()


def test_o5_5_oracle_vs_adversarial_harm_rate(tmp_path: Path):
    """
    Verify Oracle FakeLLM repairs cleanly, Adversarial FakeLLM is rejected,
    WARN-only issues produce 0 model calls, and harm rate <= 0.1%.
    """
    # 1. WARN-only document produces 0 model calls
    doc_warn = ExamDocument(
        schema_version=2,
        source_path="test_warn.pdf",
        metadata=ExamMetadata(exam_name="Warn Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700)],
        questions=[_create_test_question("q1", 1, "Question with minor warning")],
        issues=[
            Issue(
                id="w1",
                stage="s8_verify",
                rule="lexicon",
                severity=IssueSeverity.WARNING,
                message="Minor lexicon warning",
                evidence={"question_number": 1},
            )
        ],
    )
    fake_provider_warn = FakeLLMClient()
    ctx_warn = StageContext(
        document=doc_warn,
        spec=None,
        config=ExamForgeConfig(flags={"s7_repair": True}),
        stage_dir=tmp_path / "s7_warn",
        run_dir=tmp_path / "run_warn",
    )
    ctx_warn.llm_client = LLMClient(provider=fake_provider_warn)
    res_warn = S7Repair().run(ctx_warn)
    # Zero model calls for WARN
    assert len(fake_provider_warn.calls) == 0
    assert res_warn.metrics["repaired_count"] == 0

    # 2. Adversarial FakeLLM attempts forbidden paths and digit mutations
    doc_adv = ExamDocument(
        schema_version=2,
        source_path="test_adv.pdf",
        metadata=ExamMetadata(exam_name="Adv Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700)],
        questions=[_create_test_question("q1", 1, "accleration is 10 m/s^2")],
        issues=[
            Issue(
                id="i_adv",
                stage="s8_verify",
                rule="lexicon",
                severity=IssueSeverity.BLOCKER,
                message="Typo in stem",
                evidence={"question_number": 1},
            )
        ],
    )
    # Adversarial payload modifying digits and immutable path
    fake_provider_adv = FakeLLMClient(default_content=json.dumps({
        "patches": [
            {"op": "replace", "path": "/id", "value": "corrupted_id"},
            {"op": "replace", "path": "/stem_text_en", "value": "acceleration is 99 m/s^2"},
        ]
    }))
    ctx_adv = StageContext(
        document=doc_adv,
        spec=None,
        config=ExamForgeConfig(flags={"s7_repair": True}),
        stage_dir=tmp_path / "s7_adv",
        run_dir=tmp_path / "run_adv",
    )
    ctx_adv.llm_client = LLMClient(provider=fake_provider_adv)
    res_adv = S7Repair().run(ctx_adv)

    # Corrupting patch was rejected; document unchanged
    assert res_adv.document.questions[0].id == "q1"
    assert res_adv.document.questions[0].stem_text_en == "accleration is 10 m/s^2"
    assert res_adv.metrics["repaired_count"] == 0
    assert res_adv.metrics["reverted_repairs"] >= 1
    # Harm rate must be <= 0.1% (0.0 here since document was preserved)
    assert res_adv.metrics["repair_harm_rate"] <= 0.001

    # 3. Oracle FakeLLM provides valid targeted fix
    doc_oracle = ExamDocument(
        schema_version=2,
        source_path="test_ora.pdf",
        metadata=ExamMetadata(exam_name="Oracle Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700)],
        questions=[_create_test_question("q1", 1, "accleration is 10 m/s^2")],
        issues=[
            Issue(
                id="i_ora",
                stage="s8_verify",
                rule="lexicon",
                severity=IssueSeverity.BLOCKER,
                message="Typo in stem",
                evidence={"question_number": 1},
            )
        ],
    )
    fake_provider_ora = FakeLLMClient(default_content=json.dumps({
        "patches": [
            {"op": "replace", "path": "/stem_text_en", "value": "acceleration is 10 m/s^2"}
        ]
    }))
    ctx_ora = StageContext(
        document=doc_oracle,
        spec=None,
        config=ExamForgeConfig(flags={"s7_repair": True}),
        stage_dir=tmp_path / "s7_ora",
        run_dir=tmp_path / "run_ora",
    )
    ctx_ora.llm_client = LLMClient(provider=fake_provider_ora)
    res_ora = S7Repair().run(ctx_ora)

    assert res_ora.metrics["repaired_count"] == 1
    assert res_ora.document.questions[0].stem_text_en == "acceleration is 10 m/s^2"
    assert res_ora.metrics["repair_harm_rate"] <= 0.001
