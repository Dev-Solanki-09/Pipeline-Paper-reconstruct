"""Synthetic ground-truth ExamDocument generator.

Emits reproducible, seeded ExamDocument objects covering all question kinds,
content node variants, passages, tables, diagrams, and marking schemes.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from data.corpora import (
    ASSERTION_REASON_PAIRS,
    EN_QUESTIONS,
    HI_QUESTIONS,
    MATCH_ITEMS,
    PASSAGES,
)
from examforge.ir.schema import (
    AnswerSpec,
    BBox,
    Block,
    BlockStatus,
    BlockType,
    Cell,
    ContentNode,
    DocumentPart,
    ExamDocument,
    ExamMetadata,
    Figure,
    FigureClass,
    FigureNode,
    Lang,
    LanguageInfo,
    Marks,
    MatchColumnsNode,
    MathNode,
    Option,
    PageClassification,
    PageInfo,
    Passage,
    Question,
    QuestionKind,
    StatementsNode,
    Table,
    TableNode,
    TextNode,
)


class SyntheticDocumentGenerator:
    """
    Seeded generator producing valid, rich ExamDocument instances for testing,
    benchmarking, and ground-truth evaluation.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate(
        self,
        num_questions: int = 10,
        languages: list[str] | None = None,
        exam_name: str = "Synthetic Assessment Examination",
        year: int = 2026,
    ) -> ExamDocument:
        """Generate a complete synthetic ExamDocument."""
        langs = languages or ["en", "hi"]
        doc = ExamDocument(
            schema_version=2,
            source_path="synthetic://generated_exam.pdf",
            source_hash=f"synth_{self.seed}_{num_questions}",
            metadata=ExamMetadata(
                exam_name=exam_name,
                year=year,
                subject="Science",
                total_questions_expected=num_questions,
                source_type="synthetic",
            ),
            languages=[
                LanguageInfo(code=l, script="Latn" if l == "en" else "Deva", direction="ltr")
                for l in langs
            ],
        )

        # 1. Document parts (cover page, instructions, etc.)
        doc.parts = [
            DocumentPart(
                kind="cover",
                pages=[1],
            ),
            DocumentPart(
                kind="section_header",
                pages=[2, 3, 4],
            ),
            DocumentPart(
                kind="answer_key",
                pages=[5],
            ),
        ]

        # 2. Pages setup
        doc.pages = [
            PageInfo(page_number=1, width_px=595, height_px=842, classification=PageClassification.COVER),
            PageInfo(page_number=2, width_px=595, height_px=842, classification=PageClassification.QUESTIONS),
            PageInfo(page_number=3, width_px=595, height_px=842, classification=PageClassification.QUESTIONS),
            PageInfo(page_number=4, width_px=595, height_px=842, classification=PageClassification.QUESTIONS),
            PageInfo(page_number=5, width_px=595, height_px=842, classification=PageClassification.ANSWER_KEY),
        ]

        questions: list[Question] = []
        q_num = 1
        page_idx = 2

        # Include at least one passage if questions >= 4
        if num_questions >= 4:
            p_data = self.rng.choice(PASSAGES)
            p_id = f"passage_{self.seed}_1"
            p_nodes: list[ContentNode] = [
                TextNode(
                    texts={
                        "en": p_data["stem_en"],
                        "hi": p_data.get("stem_hi", ""),
                    }
                )
            ]
            passage_q_refs: list[str] = []

            for sub_idx, sub_q in enumerate(p_data["questions"]):
                q_id = f"q{q_num}"
                passage_q_refs.append(q_id)

                opts = [
                    Option(
                        label=f"({i+1})",
                        content=[
                            TextNode(
                                texts={
                                    "en": opt_en,
                                    "hi": sub_q.get("options_hi", [""] * 4)[i] if "options_hi" in sub_q else "",
                                }
                            )
                        ],
                    )
                    for i, opt_en in enumerate(sub_q["options_en"])
                ]

                q = Question(
                    id=q_id,
                    number=q_num,
                    sequence_index=q_num,
                    section="PHYSICS",
                    kind=QuestionKind.PASSAGE_BASED,
                    passage_ref=p_id,
                    stem=[
                        TextNode(
                            texts={
                                "en": sub_q["stem_en"],
                                "hi": sub_q.get("stem_hi", ""),
                            }
                        )
                    ],
                    options=opts,
                    marks=Marks(positive=4.0, negative=-1.0),
                    answer=AnswerSpec(keys=["(1)"], text="(1)", kind=QuestionKind.PASSAGE_BASED),
                    source_pages=[page_idx],
                )
                questions.append(q)
                q_num += 1

            doc.passages.append(
                Passage(
                    id=p_id,
                    nodes=p_nodes,
                    question_refs=passage_q_refs,
                )
            )

        # Include match-columns question if available
        if q_num <= num_questions and MATCH_ITEMS:
            m_data = self.rng.choice(MATCH_ITEMS)
            left_items = [{"en": f"({code}) {text}", "hi": f"({code}) {text_hi}"} for (code, text), (_, text_hi) in zip(m_data["left"], m_data["left_hi"])]
            right_items = [{"en": f"({code}) {text}", "hi": f"({code}) {text_hi}"} for (code, text), (_, text_hi) in zip(m_data["right"], m_data["right_hi"])]

            q_id = f"q{q_num}"
            q = Question(
                id=q_id,
                number=q_num,
                sequence_index=q_num,
                section="BIOLOGY",
                kind=QuestionKind.MATCH,
                stem=[
                    TextNode(texts={"en": "Match List-I with List-II and select the correct option:", "hi": "सूची-I का सूची-II से मिलान कीजिए और सही विकल्प चुनिए:"}),
                    MatchColumnsNode(left=left_items, right=right_items),
                ],
                options=[
                    Option(label="(1)", content=[TextNode(texts={"en": m_data["correct"], "hi": m_data["correct"]})]),
                    Option(label="(2)", content=[TextNode(texts={"en": "A-I, B-II, C-III, D-IV", "hi": "A-I, B-II, C-III, D-IV"})]),
                    Option(label="(3)", content=[TextNode(texts={"en": "A-III, B-I, C-IV, D-II", "hi": "A-III, B-I, C-IV, D-II"})]),
                    Option(label="(4)", content=[TextNode(texts={"en": "A-IV, B-III, C-II, D-I", "hi": "A-IV, B-III, C-II, D-I"})]),
                ],
                marks=Marks(positive=4.0, negative=-1.0),
                answer=AnswerSpec(keys=["(1)"], text="(1)", kind=QuestionKind.MATCH),
                source_pages=[page_idx],
            )
            questions.append(q)
            q_num += 1

        # Include assertion-reason question
        if q_num <= num_questions and ASSERTION_REASON_PAIRS:
            ar = self.rng.choice(ASSERTION_REASON_PAIRS)
            q_id = f"q{q_num}"
            q = Question(
                id=q_id,
                number=q_num,
                sequence_index=q_num,
                section="CHEMISTRY",
                kind=QuestionKind.ASSERTION_REASON,
                stem=[
                    StatementsNode(
                        items=[
                            {"en": ar["assertion_en"], "hi": ar["assertion_hi"]},
                            {"en": ar["reason_en"], "hi": ar["reason_hi"]},
                        ]
                    )
                ],
                options=[
                    Option(label=f"({i+1})", content=[TextNode(texts={"en": opt_en, "hi": ar["options_hi"][i]})])
                    for i, opt_en in enumerate(ar["options_en"])
                ],
                marks=Marks(positive=4.0, negative=-1.0),
                answer=AnswerSpec(keys=["(1)"], text="(1)", kind=QuestionKind.ASSERTION_REASON),
                source_pages=[page_idx],
            )
            questions.append(q)
            q_num += 1

        # Include figure-bearing question
        if q_num <= num_questions:
            fig_id = f"fig_{self.seed}_{q_num}"
            fig = Figure(
                id=fig_id,
                page=page_idx,
                bbox=BBox(x1=50.0, y1=100.0, x2=350.0, y2=260.0),
                crop_path="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                classification=FigureClass.DIAGRAM,
                question_ref=f"q{q_num}",
            )
            doc.figures.append(fig)

            q_id = f"q{q_num}"
            q = Question(
                id=q_id,
                number=q_num,
                sequence_index=q_num,
                section="PHYSICS",
                kind=QuestionKind.MCQ_SINGLE,
                stem=[
                    TextNode(texts={"en": "In the circuit diagram shown below, find the total equivalent resistance:", "hi": "नीचे दिए गए परिपथ आरेख में, कुल तुल्य प्रतिरोध ज्ञात कीजिए:"}),
                    FigureNode(figure_ref=fig_id, caption={"en": "Circuit Diagram", "hi": "परिपथ आरेख"}),
                ],
                options=[
                    Option(label="(1)", content=[TextNode(texts={"en": "5 \u03a9", "hi": "5 \u03a9"})]),
                    Option(label="(2)", content=[TextNode(texts={"en": "10 \u03a9", "hi": "10 \u03a9"})]),
                    Option(label="(3)", content=[TextNode(texts={"en": "15 \u03a9", "hi": "15 \u03a9"})]),
                    Option(label="(4)", content=[TextNode(texts={"en": "20 \u03a9", "hi": "20 \u03a9"})]),
                ],
                figure_refs=[fig_id],
                marks=Marks(positive=4.0, negative=-1.0),
                answer=AnswerSpec(keys=["(2)"], text="(2)", kind=QuestionKind.MCQ_SINGLE),
                source_pages=[page_idx],
            )
            questions.append(q)
            q_num += 1

        # Fill remaining questions with standard MCQs from corpora
        corp_len = len(EN_QUESTIONS)
        while q_num <= num_questions:
            idx = (q_num - 1) % corp_len
            en_q = EN_QUESTIONS[idx]
            hi_q = HI_QUESTIONS[idx] if idx < len(HI_QUESTIONS) else None

            q_id = f"q{q_num}"
            opts = [
                Option(
                    label=f"({i+1})",
                    content=[
                        TextNode(
                            texts={
                                "en": opt,
                                "hi": hi_q["options"][i] if hi_q else opt,
                            }
                        )
                    ],
                )
                for i, opt in enumerate(en_q["options"])
            ]

            q = Question(
                id=q_id,
                number=q_num,
                sequence_index=q_num,
                section=en_q.get("subject", "GENERAL").upper(),
                kind=QuestionKind.MCQ_SINGLE,
                stem=[
                    TextNode(
                        texts={
                            "en": en_q["stem"],
                            "hi": hi_q["stem"] if hi_q else "",
                        }
                    )
                ],
                options=opts,
                marks=Marks(positive=4.0, negative=-1.0),
                answer=AnswerSpec(keys=["(1)"], text="(1)", kind=QuestionKind.MCQ_SINGLE),
                source_pages=[page_idx],
            )
            questions.append(q)
            q_num += 1
            if q_num % 3 == 0 and page_idx < 4:
                page_idx += 1

        doc.questions = questions

        # Synthesize layout Blocks from generated questions so downstream stages can also inspect blocks
        order = 0
        blocks: list[Block] = []
        for q in questions:
            for node in q.stem:
                if isinstance(node, TextNode):
                    blocks.append(
                        Block(
                            id=f"b_{order}",
                            page=q.source_pages[0] if q.source_pages else 2,
                            type=BlockType.TEXT,
                            bbox=BBox(x1=50.0, y1=50.0 + (order * 30) % 600, x2=500.0, y2=80.0 + (order * 30) % 600),
                            order=order,
                            text=f"{q.number}. " + node.texts.get("en", ""),
                            confidence=1.0,
                            status=BlockStatus.TRUSTED,
                        )
                    )
                    order += 1
            for opt in q.options:
                opt_text = opt.label + " " + " ".join(n.texts.get("en", "") for n in opt.content if isinstance(n, TextNode))
                blocks.append(
                    Block(
                        id=f"b_{order}",
                        page=q.source_pages[0] if q.source_pages else 2,
                        type=BlockType.TEXT,
                        bbox=BBox(x1=60.0, y1=50.0 + (order * 30) % 600, x2=500.0, y2=75.0 + (order * 30) % 600),
                        order=order,
                        text=opt_text,
                        confidence=1.0,
                        status=BlockStatus.TRUSTED,
                    )
                )
                order += 1

        doc.blocks = blocks
        return doc
