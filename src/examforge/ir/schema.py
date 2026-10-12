"""
ExamForge Intermediate Representation schema.

Every engine, stage, and validator speaks this schema. It is validated
at every hand-off between stages via Pydantic model validation.

Design decisions:
- Pydantic v2 for runtime validation + JSON serialization.
- All coordinates are in pixels (bbox_px) with optional normalized form.
- Block is the atomic unit; Questions, Tables, Figures compose Blocks.
- Provenance is tracked per-block via `sources` (which engine said what).
- Status tracks trust level through the pipeline.
- Issues accumulate across stages and carry evidence for review.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BlockType(str, Enum):
    """Classification of a recognized block on a page."""

    TEXT = "text"
    FORMULA = "formula"
    FIGURE = "figure"
    TABLE = "table"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    WATERMARK = "watermark"
    LOGO = "logo"
    QR_CODE = "qr_code"
    URL = "url"
    UNKNOWN = "unknown"


class BlockStatus(str, Enum):
    """Trust level of a block's content."""

    TRUSTED = "trusted"  # Engines agree or single high-confidence reading
    DISPUTED = "disputed"  # Engines disagree, unresolved
    REPAIRED = "repaired"  # Disagreement resolved by heuristic or invariant
    HUMAN = "human"  # Manually corrected
    DROPPED = "dropped"  # Identified as furniture/watermark, removed


class Lang(str, Enum):
    EN = "en"
    HI = "hi"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class QuestionKind(str, Enum):
    MCQ_SINGLE = "mcq1"  # Single correct option
    MCQ_MULTI = "mcqn"  # Multiple correct options
    NUMERIC = "numeric"  # Numeric answer (JEE Advanced)
    MATCH = "match"  # Match-the-column
    ASSERTION = "assertion"  # Assertion-reason
    PASSAGE = "passage"  # Passage-based sub-questions
    INTEGER = "integer"  # Integer-type (JEE Advanced)


class PageClassification(str, Enum):
    COVER = "cover"
    INSTRUCTIONS = "instructions"
    QUESTIONS = "questions"
    ANSWER_KEY = "answer_key"
    ROUGH_WORK = "rough_work"
    BLANK = "blank"
    OMR = "omr"
    UNKNOWN = "unknown"


class WatermarkTier(str, Enum):
    """Watermark severity — drives the cleaning strategy."""

    W0_NONE = "none"
    W1_TEXT_LAYER = "text_layer"  # In PDF text objects only
    W2_TRANSPARENT = "transparent"  # Alpha < 0.3
    W3_SEMI_OPAQUE = "semi_opaque"  # Alpha 0.3–0.7
    W4_OPAQUE = "opaque"  # Alpha > 0.7
    W5_BAKED = "baked"  # Indistinguishable from content


class IssueSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


class PageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class FigureClass(str, Enum):
    DIAGRAM = "diagram"
    FORMULA = "formula"
    TABLE = "table"
    LOGO = "logo"
    QR = "qr"
    PHOTO = "photo"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


class BBox(BaseModel):
    """Bounding box in pixel coordinates (origin top-left)."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return self.width * self.height

    def overlap_ratio(self, other: BBox) -> float:
        """Intersection-over-union with another box."""
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        if ix1 >= ix2 or iy1 >= iy2:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0


class EngineSource(BaseModel):
    """A single engine's reading of a block."""

    engine: str  # e.g. "paddleocr", "tesseract", "docling"
    text: str = ""
    latex: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bbox: BBox | None = None


class Block(BaseModel):
    """
    Atomic unit of recognized content on a page.

    Every piece of text, formula, or detected region is a Block. Blocks carry
    multi-engine provenance (sources), a trust status, and optional crop
    references for human review.
    """

    id: str
    page: int  # 1-indexed
    type: BlockType = BlockType.TEXT
    bbox: BBox
    bbox_norm: tuple[float, float, float, float] | None = None  # (x1, y1, x2, y2) normalized to [0,1]
    order: int = 0  # reading order within the page
    lang: Lang = Lang.UNKNOWN
    text: str = ""
    latex: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sources: list[EngineSource] = Field(default_factory=list)
    crop_ref: str | None = None  # relative path to cropped image in run dir
    status: BlockStatus = BlockStatus.TRUSTED
    drop_reason: str | None = None


# ---------------------------------------------------------------------------
# Exam structure
# ---------------------------------------------------------------------------


class Option(BaseModel):
    """A single option (choice) within a question."""

    label: str  # "A", "B", "1", "2", "(1)", "(a)", etc.
    text_en: list[Block] = Field(default_factory=list)
    text_hi: list[Block] = Field(default_factory=list)
    text_str_en: str = ""  # Plaintext English option text
    text_str_hi: str = ""  # Plaintext Hindi option text
    figure_ref: str | None = None  # figure ID if option contains a figure


class Answer(BaseModel):
    """Correct answer, if answer key is in scope."""

    correct_options: list[str] = Field(default_factory=list)  # ["A"] or ["A", "C"]
    numeric_value: float | None = None
    numeric_range: tuple[float, float] | None = None


class Question(BaseModel):
    """
    A single exam question with bilingual stems, options, and references.

    Questions carry provenance back to their source pages and can reference
    figures, tables, and passages. Sub-questions (JEE Advanced) use
    parent_question / sub_question_refs.
    """

    id: str
    number: int
    section: str | None = None
    kind: QuestionKind = QuestionKind.MCQ_SINGLE
    stem_en: list[Block] = Field(default_factory=list)
    stem_hi: list[Block] = Field(default_factory=list)
    stem_text_en: str = ""  # Plaintext English question stem
    stem_text_hi: str = ""  # Plaintext Hindi question stem
    options: list[Option] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)  # figure IDs
    table_refs: list[str] = Field(default_factory=list)  # table IDs
    marks: float | None = None
    source_pages: list[int] = Field(default_factory=list)  # pages this Q spans

    # Relationships
    passage_ref: str | None = None  # parent passage ID
    parent_question: str | None = None  # parent Q ID for sub-questions
    sub_question_refs: list[str] = Field(default_factory=list)
    answer: Answer | None = None


class Cell(BaseModel):
    """A single cell in a table."""

    text: str = ""
    lang: Lang = Lang.UNKNOWN
    colspan: int = 1
    rowspan: int = 1


class Table(BaseModel):
    """A recognized table (e.g. match-the-column)."""

    id: str
    page: int
    bbox: BBox
    rows: list[list[Cell]] = Field(default_factory=list)
    sources: list[EngineSource] = Field(default_factory=list)
    status: BlockStatus = BlockStatus.TRUSTED
    question_ref: str | None = None  # question this table belongs to


class Passage(BaseModel):
    """Shared passage/stem for multiple questions (JEE/UPSC)."""

    id: str
    text_en: list[Block] = Field(default_factory=list)
    text_hi: list[Block] = Field(default_factory=list)
    question_refs: list[str] = Field(default_factory=list)


class Figure(BaseModel):
    """A detected figure/diagram with its crop and classification."""

    id: str
    page: int
    bbox: BBox
    crop_path: str | None = None  # relative path to cropped image
    format: str = "png"  # png, svg, webp
    classification: FigureClass = FigureClass.UNKNOWN
    width_mm: float | None = None  # physical width for print
    height_mm: float | None = None
    question_ref: str | None = None
    option_ref: str | None = None  # if figure belongs to a specific option
    perceptual_hash: str | None = None
    watermark_residual: float | None = None
    status: BlockStatus = BlockStatus.TRUSTED


# ---------------------------------------------------------------------------
# Page-level metadata
# ---------------------------------------------------------------------------


class PageInfo(BaseModel):
    """Per-page metadata from S0 intake."""

    page_number: int  # 1-indexed
    dpi: float | None = None
    width_px: int = 0
    height_px: int = 0
    skew_degrees: float = 0.0
    blur_score: float = 0.0  # Laplacian variance — higher = sharper
    contrast: float = 0.0
    classification: PageClassification = PageClassification.UNKNOWN
    has_text_layer: bool = False
    text_layer_valid: bool = False  # False if legacy-font gibberish detected
    legacy_fonts: list[str] = Field(default_factory=list)  # e.g. ["Kruti Dev"]
    watermark_tier: WatermarkTier = WatermarkTier.W0_NONE
    column_count: int = 1
    is_two_page_spread: bool = False
    has_annotation_ink: bool = False
    image_path: str | None = None  # relative path to rendered page image
    cleaned_image_path: str | None = None  # relative path after S2


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


class Issue(BaseModel):
    """
    A problem detected during processing.

    Issues accumulate across stages. Blockers prevent the run from
    succeeding (exit code 30). Warnings are reported but don't block.
    """

    id: str
    stage: str  # e.g. "s0_intake", "s3_dual_parse"
    page: int | None = None
    element_id: str | None = None  # block/question/figure ID
    severity: IssueSeverity = IssueSeverity.WARNING
    rule: str | None = None  # spec rule ID, e.g. "R01_no_furniture"
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False
    resolution: str | None = None


# ---------------------------------------------------------------------------
# Document root
# ---------------------------------------------------------------------------


class ExamMetadata(BaseModel):
    """Metadata harvested from cover/header before deletion."""

    exam_name: str | None = None
    year: int | None = None
    series_code: str | None = None
    date: str | None = None
    subject: str | None = None
    total_questions_expected: int | None = None
    source_type: str | None = None  # "digital", "scan", "photo", "mixed"


class ExamDocument(BaseModel):
    """
    Root document model — the complete state of a processed exam paper.

    This is the single object passed between stages. Each stage reads it,
    enriches it, and returns an updated copy. It is serialized to JSON
    after every stage as a checkpoint.
    """

    source_path: str
    source_hash: str = ""  # SHA-256 of input file
    metadata: ExamMetadata = Field(default_factory=ExamMetadata)
    pages: list[PageInfo] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    passages: list[Passage] = Field(default_factory=list)

    # Processing state
    page_statuses: dict[int, PageStatus] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)

    # Provenance
    created_at: datetime = Field(default_factory=datetime.now)
    last_stage: str | None = None

    def add_issue(self, issue: Issue) -> None:
        """Append an issue to the document."""
        self.issues.append(issue)

    def get_page_blocks(self, page: int) -> list[Block]:
        """Get all blocks for a given page, sorted by reading order."""
        return sorted(
            [b for b in self.blocks if b.page == page],
            key=lambda b: b.order,
        )

    def get_question_pages(self) -> set[int]:
        """Return the set of pages classified as question pages."""
        return {p.page_number for p in self.pages if p.classification == PageClassification.QUESTIONS}

    def blocker_issues(self) -> list[Issue]:
        """Return unresolved blocker issues."""
        return [i for i in self.issues if i.severity == IssueSeverity.BLOCKER and not i.resolved]

    def has_blockers(self) -> bool:
        return len(self.blocker_issues()) > 0
