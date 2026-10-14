"""
Tests for Phase 15: Self-Improving Loop (Lessons Store, Retrieval, and Promotion).
"""

from __future__ import annotations

from pathlib import Path

from examforge.lessons.promote import LessonPromoter
from examforge.lessons.retrieve import LessonRetriever
from examforge.lessons.store import (
    ContextFeatures,
    LessonsStore,
    normalize_issue_signature,
)


def test_signature_normalization_stability():
    """Verify issue signature normalization replaces numbers, strings, and collapses whitespace."""
    sig1 = normalize_issue_signature("r09_brackets", "Found unescaped 'x + 2' at line 42")
    sig2 = normalize_issue_signature("R09_BRACKETS", "Found   unescaped  'foo'  at line 999")
    sig3 = normalize_issue_signature("r09_brackets", "Found unescaped \"bar\" at line 12.5")

    expected = "R09_BRACKETS::Found unescaped <STR> at line <NUM>"
    assert sig1 == expected
    assert sig2 == expected
    assert sig3 == expected

    # Idempotent normalization
    assert normalize_issue_signature("R09_BRACKETS", expected.split("::")[1]) == expected


def test_lessons_store_record_and_deduplicate(tmp_path: Path):
    """Verify lessons are appended, and duplicates increment count and collect source papers."""
    store_file = tmp_path / "lessons.jsonl"
    store = LessonsStore(store_file)

    template = {"patches": [{"op": "replace", "path": "/number", "value": 5}]}
    ctx = ContextFeatures(profile_id="neet_ug", script="Deva", kind="mcq1")

    # First occurrence
    l1 = store.record_lesson(
        rule="r14_numbering",
        issue_signature="R14::Gap at <NUM>",
        fix_patch_template=template,
        fix_summary="Replaced number with 5",
        context_features=ctx,
        source_paper="paper_a.pdf",
    )
    assert l1.count == 1
    assert l1.status == "candidate"
    assert l1.source_papers == ["paper_a.pdf"]

    # Second occurrence from same paper
    l2 = store.record_lesson(
        rule="r14_numbering",
        issue_signature="R14::Gap at <NUM>",
        fix_patch_template=template,
        fix_summary="Replaced number with 5",
        context_features=ctx,
        source_paper="paper_a.pdf",
    )
    assert l2.id == l1.id
    assert l2.count == 2
    assert l2.source_papers == ["paper_a.pdf"]

    # Third occurrence from a different paper
    l3 = store.record_lesson(
        rule="r14_numbering",
        issue_signature="R14::Gap at <NUM>",
        fix_patch_template=template,
        fix_summary="Replaced number with 5",
        context_features=ctx,
        source_paper="paper_b.pdf",
    )
    assert l3.id == l1.id
    assert l3.count == 3
    assert set(l3.source_papers) == {"paper_a.pdf", "paper_b.pdf"}


def test_lessons_store_corrupt_line_tolerance(tmp_path: Path):
    """Verify store skips corrupt lines in JSONL with a warning without crashing."""
    store_file = tmp_path / "lessons.jsonl"
    store = LessonsStore(store_file)

    template = {"patches": []}
    store.record_lesson(
        rule="r01",
        issue_signature="R01::A",
        fix_patch_template=template,
        source_paper="p1.pdf",
    )

    # Invalidate one line in the middle
    with open(store_file, "a", encoding="utf-8") as f:
        f.write("\n{CORRUPTED_JSON_LINE\n")

    store.record_lesson(
        rule="r02",
        issue_signature="R02::B",
        fix_patch_template=template,
        source_paper="p2.pdf",
    )

    all_lessons = store.list_lessons()
    assert len(all_lessons) == 2
    rules = {lsn.rule for lsn in all_lessons}
    assert rules == {"r01", "r02"}


def test_lessons_store_compaction_and_retirement(tmp_path: Path):
    """Verify compaction collapses duplicate signatures and enforces size cap on retired."""
    store_file = tmp_path / "lessons.jsonl"
    store = LessonsStore(store_file)

    template = {"patches": [{"op": "add", "path": "/tags", "value": "math"}]}
    l1 = store.record_lesson(
        rule="r05",
        issue_signature="R05::Missing math",
        fix_patch_template=template,
        source_paper="p1.pdf",
    )
    l2 = store.record_lesson(
        rule="r06",
        issue_signature="R06::Missing tag",
        fix_patch_template=template,
        source_paper="p2.pdf",
    )

    # Retire l1
    store.update_lesson_status(l1.id, "retired")
    assert store.get_lesson(l1.id).status == "retired"

    # Compact with max_records=1 -> non-retired l2 preserved, retired l1 pruned
    remaining_count = store.compact(max_records=1)
    assert remaining_count == 1
    assert store.get_lesson(l2.id) is not None
    assert store.get_lesson(l1.id) is None


def test_lesson_retriever_ranking_and_token_cap(tmp_path: Path):
    """Verify retriever filters retired, ranks by relevance/context, and respects token caps."""
    store_file = tmp_path / "lessons.jsonl"
    store = LessonsStore(store_file)

    t_patch = {"patches": [{"op": "replace", "path": "/stem/0/text", "value": "Fixed"}]}

    # Lesson 1: Hindi/Deva matching
    l1 = store.record_lesson(
        rule="r09",
        issue_signature="R09::Invalid Hindi bracket in question",
        fix_patch_template=t_patch,
        context_features=ContextFeatures(profile_id="neet", script="Deva", kind="mcq1"),
        source_paper="p1.pdf",
    )
    # Lesson 2: English/Latn
    store.record_lesson(
        rule="r09",
        issue_signature="R09::Invalid English bracket in statement",
        fix_patch_template=t_patch,
        context_features=ContextFeatures(profile_id="neet", script="Latn", kind="mcq1"),
        source_paper="p2.pdf",
    )
    # Lesson 3: Retired
    l3 = store.record_lesson(
        rule="r09",
        issue_signature="R09::Old bracket error",
        fix_patch_template=t_patch,
        source_paper="p3.pdf",
    )
    store.update_lesson_status(l3.id, "retired")

    retriever = LessonRetriever(store)

    # Query with Deva context
    results = retriever.retrieve(
        rule="r09",
        context=ContextFeatures(profile_id="neet", script="Deva", kind="mcq1"),
        query_text="Hindi bracket issue",
        top_k=5,
        token_budget=500,
    )

    # Should not include retired l3
    result_ids = [r.id for r in results]
    assert l3.id not in result_ids
    assert l1.id in result_ids
    # l1 should be ranked first due to Deva script boost + query overlap
    assert results[0].id == l1.id

    # Test token budget constraint
    small_budget_results = retriever.retrieve(
        rule="r09",
        context=ContextFeatures(profile_id="neet", script="Deva", kind="mcq1"),
        query_text="Hindi bracket issue",
        top_k=5,
        token_budget=5,  # Very small budget allowing at most 1 lesson
    )
    assert len(small_budget_results) == 1


def test_lesson_promoter_threshold_and_generation(tmp_path: Path):
    """
    Verify promotion triggers only when recurrence >= 3 across >= 2 papers,
    generating proposal.
    """
    store_file = tmp_path / "lessons.jsonl"
    proposals_dir = tmp_path / "proposals"
    store = LessonsStore(store_file)
    promoter = LessonPromoter(
        store,
        proposals_dir=proposals_dir,
        min_recurrence=3,
        min_papers=2,
    )

    template = {"patches": [{"op": "replace", "path": "/kind", "value": "mcq4"}]}
    ctx = ContextFeatures(profile_id="jee_main", script="Latn", kind="mcq1")

    # Case 1: Recurrence = 2, Papers = 2 (not enough recurrence)
    store.record_lesson(
        rule="r11_kind",
        issue_signature="R11::Kind mismatch <NUM>",
        fix_patch_template=template,
        context_features=ctx,
        source_paper="paper1.pdf",
    )
    l1 = store.record_lesson(
        rule="r11_kind",
        issue_signature="R11::Kind mismatch <NUM>",
        fix_patch_template=template,
        context_features=ctx,
        source_paper="paper2.pdf",
    )

    proposals = promoter.scan_and_promote()
    assert len(proposals) == 0
    assert store.get_lesson(l1.id).status == "candidate"

    # Case 2: Recurrence = 3, but all from paper1 (not enough distinct papers)
    l_single = store.record_lesson(
        rule="r12_opt",
        issue_signature="R12::Missing opt <NUM>",
        fix_patch_template=template,
        context_features=ctx,
        source_paper="single_paper.pdf",
    )
    store.record_lesson(
        rule="r12_opt",
        issue_signature="R12::Missing opt <NUM>",
        fix_patch_template=template,
        context_features=ctx,
        source_paper="single_paper.pdf",
    )
    store.record_lesson(
        rule="r12_opt",
        issue_signature="R12::Missing opt <NUM>",
        fix_patch_template=template,
        context_features=ctx,
        source_paper="single_paper.pdf",
    )
    assert store.get_lesson(l_single.id).count >= 3
    assert len(store.get_lesson(l_single.id).source_papers) == 1

    proposals = promoter.scan_and_promote()
    assert len(proposals) == 0

    # Case 3: Add third recurrence to l1 from paper2 -> count=3, papers=2
    store.record_lesson(
        rule="r11_kind",
        issue_signature="R11::Kind mismatch <NUM>",
        fix_patch_template=template,
        context_features=ctx,
        source_paper="paper2.pdf",
    )

    proposals = promoter.scan_and_promote()
    assert len(proposals) == 1
    prop_path = proposals[0]
    assert prop_path.exists()
    assert prop_path.name == f"{l1.id}.md"

    # Lesson should now be marked promoted
    assert store.get_lesson(l1.id).status == "promoted"

    # Verify content of generated proposal
    content = prop_path.read_text(encoding="utf-8")
    assert f"Proposal: Promote Lesson {l1.id}" in content
    assert "r11_kind" in content
    assert "Generated Runnable Pytest Verification" in content
    assert f"def test_promoted_rule_{l1.id}():" in content
    assert "Draft Rule Implementation" in content
    assert "apply_deterministic_r11_kind_rule" in content
    assert "Production code is never modified automatically" in content
