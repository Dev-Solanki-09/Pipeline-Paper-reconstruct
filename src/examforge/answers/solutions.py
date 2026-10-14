"""Solution parsing and binding to ExamDocument questions."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any

from examforge.answers.bind import find_matching_question
from examforge.answers.parse_key import _to_int
from examforge.ir.schema import (
    ContentNode,
    ExamDocument,
    FigureNode,
    MathNode,
    TextNode,
)

logger = logging.getLogger(__name__)

_SOL_HEADER_RE = re.compile(
    r"(?:^|\n)(?:(?:Sol(?:ution|\.)?|हल|Explanation|उत्तर)\s*[:.\-]?\s*(\d+|[०-९]+)|(\d+|[०-९]+)\s*[:.\-]\s*(?:Sol(?:ution|\.)?|हल|Explanation|उत्तर))\s*[:.\-]?",
    re.IGNORECASE,
)

_MATH_RE = re.compile(r"\$\$([^\$]+)\$\$|\$([^\$]+)\$")
_FIGURE_RE = re.compile(r"\[Figure:\s*([a-zA-Z0-9_\-]+)\]", re.IGNORECASE)


@dataclass
class SolutionBlock:
    """A recognized solution block for a question."""

    question_number: int
    section: str | None = None
    raw_text: str = ""


def parse_solution_blocks(text: str) -> list[SolutionBlock]:
    """Parse raw text to identify solution blocks by question number."""
    blocks: list[SolutionBlock] = []
    matches = list(_SOL_HEADER_RE.finditer(text))
    if not matches:
        return blocks

    for i, m in enumerate(matches):
        q_str = m.group(1) or m.group(2)
        q_num = _to_int(q_str)
        start_idx = m.end()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block_content = text[start_idx:end_idx].strip()
        blocks.append(
            SolutionBlock(
                question_number=q_num,
                raw_text=block_content,
            )
        )

    return blocks


def solution_text_to_nodes(text: str) -> list[ContentNode]:
    """
    Convert raw solution text into ContentNode elements (TextNode, MathNode, FigureNode).
    """
    nodes: list[ContentNode] = []
    if not text.strip():
        return nodes

    last_idx = 0
    for match in _MATH_RE.finditer(text):
        pre_text = text[last_idx : match.start()].strip()
        if pre_text:
            nodes.extend(_text_to_text_or_fig_nodes(pre_text))

        code = match.group(1) or match.group(2) or ""
        display = match.group(1) is not None
        nodes.append(
            MathNode(
                notation="latex",
                code=code.strip(),
                display=display,
            )
        )
        last_idx = match.end()

    tail_text = text[last_idx:].strip()
    if tail_text:
        nodes.extend(_text_to_text_or_fig_nodes(tail_text))

    return nodes


def _text_to_text_or_fig_nodes(text: str) -> list[ContentNode]:
    """Sub-helper to parse text and inline figure references."""
    nodes: list[ContentNode] = []
    last_idx = 0
    for match in _FIGURE_RE.finditer(text):
        pre_text = text[last_idx : match.start()].strip()
        if pre_text:
            nodes.append(_make_text_node(pre_text))
        fig_id = match.group(1)
        nodes.append(FigureNode(figure_ref=fig_id))
        last_idx = match.end()

    tail = text[last_idx:].strip()
    if tail:
        nodes.append(_make_text_node(tail))
    return nodes


def _make_text_node(text: str) -> TextNode:
    """Create a TextNode assigning 'hi' or 'en' based on script detection."""
    is_hindi = bool(re.search(r"[\u0900-\u097F]", text))
    lang_key = "hi" if is_hindi else "en"
    return TextNode(texts={lang_key: text})


def bind_solutions(
    document: ExamDocument,
    solutions_text: str | list[SolutionBlock],
) -> int:
    """
    Parse solution blocks and bind them as ContentNode lists to questions.

    Returns the count of questions with bound solutions.
    """
    if isinstance(solutions_text, str):
        blocks = parse_solution_blocks(solutions_text)
    else:
        blocks = solutions_text

    bound_count = 0
    for block in blocks:
        q = find_matching_question(
            document.questions,
            block.question_number,
            block.section,
        )
        if not q:
            logger.debug("No question found for solution Q%d", block.question_number)
            continue

        nodes = solution_text_to_nodes(block.raw_text)
        q.solution = nodes
        if q.answer and not q.answer.text_solution:
            q.answer.text_solution = block.raw_text
        bound_count += 1

    return bound_count
