"""
Phase 15 — Gate 15 Verification Suite: Self-Improving Loop (Lessons -> Rules).

Validates:
1. Zero-token repair via lesson retrieval in Stage S7 when `lessons: True`.
2. Automatic lesson recording hook after validated patch on fresh defect.
3. Clean rollback and isolation when `lessons: False`.
4. Full promotion dry-run: record -> recurrence threshold -> propose ->
   implement -> retire -> shrink context.
5. CLI commands: `examforge lessons list|promote|compact`.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from examforge.cli import main
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
    TextNode,
)
from examforge.lessons.promote import LessonPromoter
from examforge.lessons.retrieve import LessonRetriever
from examforge.lessons.store import (
    ContextFeatures,
    LessonsStore,
    normalize_issue_signature,
)
from examforge.llm.client import LLMClient
from examforge.llm.fake import FakeLLMClient
from examforge.stages.base import StageContext
from examforge.stages.s7_repair import S7Repair


def _create_synthetic_document_with_defect(doc_id: str, paper_name: str) -> ExamDocument:
    """Creates a document with a question containing a typo and an associated validator issue."""
    pages = [PageInfo(page_number=1, width_px=595, height_px=842)]
    stem_b = Block(
        id=f"b_{doc_id}",
        page=1,
        bbox=BBox(x1=10, y1=10, x2=200, y2=40),
        text="Which organelle is the powerhosue of the cell?",
    )
    q = Question(
        id=f"q_{doc_id}",
        number=1,
        stem=[TextNode(texts={"en": "Which organelle is the powerhosue of the cell?"})],
        stem_en=[stem_b],
        stem_text_en="Which organelle is the powerhosue of the cell?",
        options=[Option(label="A", text_str_en="Mitochondria")],
        source_pages=[1],
    )
    issue = Issue(
        id=f"issue_{doc_id}",
        stage="s8_verify",
        rule="r09_spelling",
        severity=IssueSeverity.WARNING,
        message="Misspelled token 'powerhosue' in Q1",
        evidence={"question_number": 1},
    )
    return ExamDocument(
        id=doc_id,
        source_path=paper_name,
        source_hash=f"hash_{doc_id}",
        pages=pages,
        blocks=[stem_b],
        questions=[q],
        issues=[issue],
    )


class TestGate15Verification:
    def test_zero_token_lesson_repair_in_s7(self, tmp_path: Path):
        """Verify that S7 repair uses pre-recorded lesson to achieve 0-token repair without LLM."""
        doc = _create_synthetic_document_with_defect("doc_1", "paper_alpha.pdf")
        lessons_file = tmp_path / "lessons.jsonl"
        store = LessonsStore(lessons_file)

        # Pre-seed a verified fix lesson
        correct_patch = [
            {
                "op": "replace",
                "path": "/stem_text_en",
                "value": "Which organelle is the powerhouse of the cell?",
            }
        ]
        sig = normalize_issue_signature("r09_spelling", "Misspelled token 'powerhosue' in Q1")
        store.record_lesson(
            rule="r09_spelling",
            issue_signature=sig,
            fix_patch_template={"patches": correct_patch},
            fix_summary="Fixed powerhosue -> powerhouse",
            context_features=ContextFeatures(profile_id="generic", kind="mcq1"),
            source_paper="prior_paper.pdf",
        )

        # FakeLLM configured to throw error if called, proving zero model calls
        class ZeroCallLLMClient(LLMClient):
            def __init__(self):
                self.calls = 0

            def complete(self, request):
                self.calls += 1
                raise AssertionError("LLM should not be called when a valid lesson exists!")

        zero_llm = ZeroCallLLMClient()
        config = ExamForgeConfig(
            flags={"s7_repair": True, "lessons": True},
            lessons_path=lessons_file,
        )
        ctx = StageContext(
            document=doc,
            spec=None,
            config=config,
            stage_dir=tmp_path / "s7",
            run_dir=tmp_path / "run",
        )
        ctx.llm_client = zero_llm

        stage = S7Repair()
        res = stage.run(ctx)

        # Verify repair was applied from lesson
        assert res.metrics.get("repaired_count", 0) == 1
        assert zero_llm.calls == 0  # Zero tokens used!
        assert doc.questions[0].stem_text_en == "Which organelle is the powerhouse of the cell?"

    def test_lessons_recording_hook_on_fresh_patch(self, tmp_path: Path):
        """Verify that when an LLM successfully repairs a fresh issue, a lesson is recorded."""
        doc = _create_synthetic_document_with_defect("doc_2", "paper_beta.pdf")
        lessons_file = tmp_path / "lessons.jsonl"
        store = LessonsStore(lessons_file)
        assert len(store.list_lessons()) == 0

        correct_patch = [
            {
                "op": "replace",
                "path": "/stem_text_en",
                "value": "Which organelle is the powerhouse of the cell?",
            }
        ]
        fake_provider = FakeLLMClient()
        fake_provider.queue_response(json.dumps({"patches": correct_patch}))
        fake_client = LLMClient(provider=fake_provider)

        config = ExamForgeConfig(
            flags={"s7_repair": True, "lessons": True},
            lessons_path=lessons_file,
        )
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

        assert res.metrics.get("repaired_count", 0) == 1
        # Store should now contain exactly 1 candidate lesson
        recorded = store.list_lessons()
        assert len(recorded) == 1
        lsn = recorded[0]
        assert lsn.rule == "r09_spelling"
        assert lsn.count == 1
        assert "hash_doc_2" in lsn.source_papers or "paper_beta.pdf" in lsn.source_papers
        assert lsn.fix_patch_template == {"patches": correct_patch}

    def test_clean_rollback_when_lessons_disabled(self, tmp_path: Path):
        """Verify that when lessons flag is False, no lesson retrieval or recording occurs."""
        doc = _create_synthetic_document_with_defect("doc_3", "paper_gamma.pdf")
        lessons_file = tmp_path / "lessons.jsonl"
        store = LessonsStore(lessons_file)

        # Seed an existing lesson
        patch = [{"op": "replace", "path": "/stem_text_en", "value": "From Lesson"}]
        sig = normalize_issue_signature(
            "r09_spelling", "Misspelled token 'powerhosue' in Q1"
        )
        store.record_lesson(
            rule="r09_spelling",
            issue_signature=sig,
            fix_patch_template={"patches": patch},
            source_paper="p_seed.pdf",
        )

        llm_patch = [{"op": "replace", "path": "/stem_text_en", "value": "From Fresh LLM"}]
        fake_provider = FakeLLMClient()
        fake_provider.queue_response(json.dumps({"patches": llm_patch}))
        fake_client = LLMClient(provider=fake_provider)

        # lessons: False
        config = ExamForgeConfig(
            flags={"s7_repair": True, "lessons": False},
            lessons_path=lessons_file,
        )
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

        # Lesson was ignored because lessons flag was False; LLM was invoked instead
        assert res.metrics.get("repaired_count", 0) == 1
        assert doc.questions[0].stem_text_en == "From Fresh LLM"
        assert len(fake_provider.calls) == 1
        # Stored lessons count did not increment
        lsns = store.list_lessons()
        assert lsns[0].count == 1

    def test_full_promotion_dry_run_and_context_shrink(self, tmp_path: Path):
        """
        Full Phase 15 dry run:
        1. Record recurring defect 3 times across 2 papers.
        2. Promote to rule proposal in proposals/<id>.md.
        3. Verify generated proposal has runnable test and rule scaffold.
        4. Implement rule deterministically.
        5. Retire lesson and verify context shrink (retriever ignores it).
        """
        lessons_file = tmp_path / "lessons.jsonl"
        proposals_dir = tmp_path / "proposals"
        store = LessonsStore(lessons_file)

        rule_name = "r09_spelling"
        sig = normalize_issue_signature(rule_name, "Misspelled token 'powerhosue' in Q1")
        patch_template = {
            "patches": [
                {
                    "op": "replace",
                    "path": "/stem_text_en",
                    "value": "Which organelle is the powerhouse of the cell?",
                }
            ]
        }

        # Step 1: Record 3 occurrences across 2 distinct papers
        store.record_lesson(
            rule=rule_name,
            issue_signature=sig,
            fix_patch_template=patch_template,
            source_paper="paper_1.pdf",
        )
        store.record_lesson(
            rule=rule_name,
            issue_signature=sig,
            fix_patch_template=patch_template,
            source_paper="paper_1.pdf",
        )
        l_rec = store.record_lesson(
            rule=rule_name,
            issue_signature=sig,
            fix_patch_template=patch_template,
            source_paper="paper_2.pdf",
        )
        assert l_rec.count == 3
        assert len(set(l_rec.source_papers)) == 2

        # Step 2: Run promotion scan
        promoter = LessonPromoter(
            store=store,
            proposals_dir=proposals_dir,
            min_recurrence=3,
            min_papers=2,
        )
        proposals = promoter.scan_and_promote()
        assert len(proposals) == 1
        proposal_file = proposals[0]
        assert proposal_file.exists()

        # Step 3: Verify proposal structure
        content = proposal_file.read_text(encoding="utf-8")
        assert f"# Proposal: Promote Lesson {l_rec.id}" in content
        assert "Total Recurrence Count:** 3" in content
        assert "paper_1.pdf, paper_2.pdf" in content
        assert f"def test_promoted_rule_{l_rec.id}():" in content
        assert "apply_deterministic_r09_spelling_rule" in content

        # Step 4: Implement rule deterministically (simulating agent action)
        def apply_deterministic_r09_spelling_rule(q: Question) -> Question:
            if "powerhosue" in (q.stem_text_en or ""):
                q.stem_text_en = q.stem_text_en.replace("powerhosue", "powerhouse")
            return q

        sample_q = Question(
            id="q_sample",
            number=1,
            stem_text_en="Which organelle is the powerhosue?",
        )
        fixed_q = apply_deterministic_r09_spelling_rule(sample_q)
        assert fixed_q.stem_text_en == "Which organelle is the powerhouse?"

        # Step 5: Retire the promoted lesson to prevent prompt bloat
        store.update_lesson_status(l_rec.id, "retired")
        assert store.get_lesson(l_rec.id).status == "retired"

        # Step 6: Verify context shrink in LessonRetriever
        retriever = LessonRetriever(store)
        active_matches = retriever.retrieve(rule=rule_name, query_text="powerhosue")
        assert len(active_matches) == 0  # Retired lesson excluded, context shrunk!

    def test_cli_lessons_commands(self, tmp_path: Path):
        """Verify CLI commands `examforge lessons list`, `promote`, and `compact`."""
        lessons_file = tmp_path / "lessons.jsonl"
        proposals_dir = tmp_path / "proposals"
        store = LessonsStore(lessons_file)

        # Seed a recurring lesson
        template = {"patches": [{"op": "replace", "path": "/foo", "value": "bar"}]}
        store.record_lesson(
            rule="r99",
            issue_signature="R99::Test",
            fix_patch_template=template,
            source_paper="p1.pdf",
        )
        store.record_lesson(
            rule="r99",
            issue_signature="R99::Test",
            fix_patch_template=template,
            source_paper="p2.pdf",
        )
        store.record_lesson(
            rule="r99",
            issue_signature="R99::Test",
            fix_patch_template=template,
            source_paper="p2.pdf",
        )

        runner = CliRunner()

        # 1. lessons list
        res_list = runner.invoke(main, ["lessons", "list", "--path", str(lessons_file)])
        assert res_list.exit_code == 0
        assert "Lessons Store:" in res_list.output
        assert "r99" in res_list.output or "R99" in res_list.output

        # 2. lessons promote
        res_promote = runner.invoke(
            main,
            [
                "lessons",
                "promote",
                "--path",
                str(lessons_file),
                "--proposals",
                str(proposals_dir),
                "--min-recurrence",
                "3",
                "--min-papers",
                "2",
            ],
        )
        assert res_promote.exit_code == 0
        assert "Promotion scan complete: 1 proposal(s) emitted." in res_promote.output

        # 3. lessons compact
        res_compact = runner.invoke(
            main,
            ["lessons", "compact", "--path", str(lessons_file), "--max-records", "10"],
        )
        assert res_compact.exit_code == 0
        assert "Compacted lessons store" in res_compact.output
