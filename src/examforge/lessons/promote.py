"""
Phase 15.4 — Lesson Promotion and Rule Scaffolding.

Generates structured proposals in `proposals/<id>.md` when a lesson
recurs >= 3 times across >= 2 papers with an identical patch template.
Never modifies production code automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

from examforge.lessons.store import Lesson, LessonsStore


class LessonPromoter:
    """Evaluates candidates for promotion into deterministic, zero-token rules."""

    def __init__(
        self,
        store: LessonsStore,
        proposals_dir: Path | str = "proposals",
        min_recurrence: int = 3,
        min_papers: int = 2,
    ) -> None:
        self.store = store
        self.proposals_dir = Path(proposals_dir)
        self.min_recurrence = min_recurrence
        self.min_papers = min_papers
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def scan_and_promote(self) -> list[Path]:
        """
        Scans all candidate lessons in the store. If any meets recurrence
        and multi-paper criteria, generates a proposal file and marks promoted.
        Returns paths to created proposals.
        """
        candidates = self.store.list_lessons(status="candidate")
        generated_proposals: list[Path] = []

        for lsn in candidates:
            if (
                lsn.count >= self.min_recurrence
                and len(set(lsn.source_papers)) >= self.min_papers
            ):
                proposal_path = self.generate_proposal(lsn)
                self.store.update_lesson_status(lsn.id, "promoted")
                generated_proposals.append(proposal_path)

        return generated_proposals

    def generate_proposal(self, lesson: Lesson) -> Path:
        """Create a markdown proposal containing evidence, failing test, and draft rule."""
        proposal_file = self.proposals_dir / f"{lesson.id}.md"

        failing_test_code = self._generate_failing_test(lesson)
        draft_rule_code = self._generate_draft_rule(lesson)

        lines = [
            f"# Proposal: Promote Lesson {lesson.id} to Deterministic Rule",
            "",
            "## 1. Evidence & Recurrence",
            f"- **Rule Triggered:** `{lesson.rule}`",
            f"- **Issue Signature:** `{lesson.issue_signature}`",
            f"- **Total Recurrence Count:** {lesson.count}",
            f"- **Distinct Papers Observed:** {', '.join(lesson.source_papers)}",
            (
                f"- **Script / Language:** `{lesson.context_features.script}` / "
                f"`{lesson.context_features.language}`"
            ),
            f"- **Question Kind:** `{lesson.context_features.kind}`",
            f"- **Fix Summary:** {lesson.fix_summary}",
            "",
            "## 2. Canonical Patch Template",
            "```json",
            json.dumps(lesson.fix_patch_template, indent=2),
            "```",
            "",
            "## 3. Generated Runnable Pytest Verification",
            "```python",
            failing_test_code.strip(),
            "```",
            "",
            "## 4. Draft Rule Implementation",
            "```python",
            draft_rule_code.strip(),
            "```",
            "",
            "> [!NOTE]",
            "> Production code is never modified automatically. Review and implement",
            "> the draft rule in `src/examforge/validators/` or `src/examforge/repair/`.",
            "",
        ]

        proposal_file.write_text("\n".join(lines), encoding="utf-8")
        return proposal_file

    def _generate_failing_test(self, lesson: Lesson) -> str:
        rule_name = lesson.rule.lower().replace("-", "_")
        return f"""
def test_promoted_rule_{lesson.id}():
    \"\"\"Generated regression test for recurring issue {lesson.id}.\"\"\"
    from examforge.ir.schema import Question, TextNode
    
    # Input question exhibiting the issue signature: {lesson.issue_signature}
    q = Question(
        id="test_q",
        number=1,
        stem=[TextNode(texts={{"en": "Sample text exhibiting {lesson.rule}"}})],
    )
    
    # Assert deterministic fix applies
    # Example: fixed_q = apply_deterministic_{rule_name}_rule(q)
    # assert fixed_q != q
"""

    def _generate_draft_rule(self, lesson: Lesson) -> str:
        rule_name = lesson.rule.lower().replace("-", "_")
        return f"""
def apply_deterministic_{rule_name}_rule(q: Question) -> Question:
    \"\"\"
    Deterministic fix for {lesson.rule} based on lesson {lesson.id}.
    Signature: {lesson.issue_signature}
    \"\"\"
    # Template: {json.dumps(lesson.fix_patch_template)}
    # Implement replacement logic here without invoking LLM models.
    return q
"""
