"""
ExamForge Intermediate Representation schema v2.

Every engine, stage, and validator speaks this schema. It is validated
at every hand-off between stages via Pydantic model validation.

Design decisions (v2):
- Pydantic v2 for runtime validation + JSON serialization.
- ContentNode discriminated union for universal question representation.
- schema_version = 2 default, with complete backward compatibility for v1 fields.
- Deterministic serialization (no timestamps or absolute paths).
- Block is layout unit; ContentNode is semantic content unit.
- Multi-engine provenance, confidence, and trust statuses tracked per block and question.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BlockType(StrEnum):
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


class BlockStatus(StrEnum):
    """Trust level of a block's content."""

    TRUSTED = "trusted"
    DISPUTED = "disputed"
    REPAIRED = "repaired"
    HUMAN = "human"
    DROPPED = "dropped"


class Lang(StrEnum):
    EN = "en"
    HI = "hi"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class QuestionKind(StrEnum):
    # v1 member names (backward compatibility)
    MCQ_SINGLE = "mcq1"
    MCQ_MULTI = "mcqn"
    NUMERIC = "numeric"
    MATCH = "match"
    ASSERTION = "assertion"
    PASSAGE = "passage"
    INTEGER = "integer"

    # v2 member names
    SINGLE_CORRECT = "mcq1"
    MULTI_CORRECT = "mcqn"
    NUMERICAL = "numeric"
    ASSERTION_REASON = "assertion"
    STATEMENT_BASED = "statement_based"
    PASSAGE_BASED = "passage"
    FILL_BLANK = "fill_blank"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    OTHER = "other"


class PageClassification(StrEnum):
    COVER = "cover"
    INSTRUCTIONS = "instructions"
    QUESTIONS = "questions"
    ANSWER_KEY = "answer_key"
    ROUGH_WORK = "rough_work"
    BLANK = "blank"
    OMR = "omr"
    UNKNOWN = "unknown"


class WatermarkTier(StrEnum):
    """Watermark severity — drives the cleaning strategy."""

    W0_NONE = "none"
    W1_TEXT_LAYER = "text_layer"
    W2_TRANSPARENT = "transparent"
    W3_SEMI_OPAQUE = "semi_opaque"
    W4_OPAQUE = "opaque"
    W5_BAKED = "baked"


class IssueSeverity(StrEnum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


class PageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PageProcessingPath(StrEnum):
    """Execution path chosen per page for optimal throughput (Phase O2)."""

    PATH_A = "path_a"  # Digital with valid text layer (zero vision model inference)
    PATH_B = "path_b"  # Scanned / raster image (classical line recognizer / selective VLM)
    PATH_C = "path_c"  # Digital with broken/legacy fonts (glyph-level font decode)


class FigureClass(StrEnum):
    DIAGRAM = "diagram"
    FORMULA = "formula"
    TABLE = "table"
    LOGO = "logo"
    QR = "qr"
    PHOTO = "photo"
    UNKNOWN = "unknown"


class Provenance(StrEnum):
    """Origin of a question or piece of content."""

    EXTRACTED = "extracted"
    BANK = "bank"
    REPAIRED = "repaired"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# Building blocks & Content Nodes
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

    engine: str
    text: str = ""
    latex: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bbox: BBox | None = None


class Block(BaseModel):
    """
    Atomic unit of recognized content on a page.

    Every piece of text, formula, or detected region is a Block.
    """

    id: str
    page: int
    type: BlockType = BlockType.TEXT
    bbox: BBox
    bbox_norm: tuple[float, float, float, float] | None = None
    order: int = 0
    lang: Lang = Lang.UNKNOWN
    text: str = ""
    latex: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sources: list[EngineSource] = Field(default_factory=list)
    crop_ref: str | None = None
    status: BlockStatus = BlockStatus.TRUSTED
    drop_reason: str | None = None


class Cell(BaseModel):
    """A single cell in a table."""

    text: str = ""
    lang: Lang | str = Lang.UNKNOWN
    colspan: int = 1
    rowspan: int = 1


# Universal ContentNode Family (v2 discriminated union)
class TextNode(BaseModel):
    kind: Literal["text"] = "text"
    texts: dict[str, str] = Field(default_factory=dict)
    style: str | None = None


class MathNode(BaseModel):
    kind: Literal["math"] = "math"
    notation: Literal["latex", "mhchem"] = "latex"
    code: str = ""
    display: bool = False
    texts: dict[str, str] = Field(default_factory=dict)


class TableNode(BaseModel):
    kind: Literal["table"] = "table"
    rows: list[list[Cell]] = Field(default_factory=list)
    header_rows: int = 0
    spans: list[dict[str, Any]] = Field(default_factory=list)


class FigureNode(BaseModel):
    kind: Literal["figure"] = "figure"
    figure_ref: str = ""
    caption: dict[str, str] = Field(default_factory=dict)


class StatementsNode(BaseModel):
    kind: Literal["statements"] = "statements"
    items: list[dict[str, str]] = Field(default_factory=list)


class MatchColumnsNode(BaseModel):
    kind: Literal["match_columns"] = "match_columns"
    left: list[dict[str, str]] = Field(default_factory=list)
    right: list[dict[str, str]] = Field(default_factory=list)


class CodeNode(BaseModel):
    kind: Literal["code"] = "code"
    language: str = ""
    text: str = ""


class BlankNode(BaseModel):
    kind: Literal["blank"] = "blank"
    index: int = 1
    expected_type: str = "text"


class RawCropNode(BaseModel):
    kind: Literal["raw_crop"] = "raw_crop"
    figure_ref: str = ""
    reason: str = ""


ContentNode = Annotated[
    TextNode
    | MathNode
    | TableNode
    | FigureNode
    | StatementsNode
    | MatchColumnsNode
    | CodeNode
    | BlankNode
    | RawCropNode,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Exam structure
# ---------------------------------------------------------------------------


class Marks(BaseModel):
    """Grading / marking scheme for a question."""

    positive: float = 4.0
    negative: float = 1.0
    partial: float | None = None


class AnswerSpec(BaseModel):
    """Detailed answer specification and range."""

    correct_options: list[str] = Field(default_factory=list)
    numeric_value: float | None = None
    numeric_range: tuple[float, float] | None = None
    text_solution: str | None = None


class Option(BaseModel):
    """A single option (choice) within a question."""

    label: str
    content: list[ContentNode] = Field(default_factory=list)
    text_en: list[Block] = Field(default_factory=list)
    text_hi: list[Block] = Field(default_factory=list)
    text_str_en: str = ""
    text_str_hi: str = ""
    figure_ref: str | None = None

    @model_validator(mode="after")
    def sync_v1_v2_texts(self) -> Option:
        """Bi-directional sync between v1 plaintext and v2 ContentNodes."""
        # Synthesize text_str from content if content exists but string is empty
        if self.content:
            en_parts: list[str] = []
            hi_parts: list[str] = []
            for node in self.content:
                if isinstance(node, TextNode):
                    if "en" in node.texts:
                        en_parts.append(node.texts["en"])
                    if "hi" in node.texts:
                        hi_parts.append(node.texts["hi"])
                elif isinstance(node, MathNode):
                    en_parts.append(node.code)
                    hi_parts.append(node.code)
            if en_parts and not self.text_str_en:
                self.text_str_en = " ".join(en_parts).strip()
            if hi_parts and not self.text_str_hi:
                self.text_str_hi = " ".join(hi_parts).strip()

        # Synthesize content from text_str if content is empty but string exists
        elif self.text_str_en or self.text_str_hi:
            texts: dict[str, str] = {}
            if self.text_str_en:
                texts["en"] = self.text_str_en
            if self.text_str_hi:
                texts["hi"] = self.text_str_hi
            self.content = [TextNode(texts=texts)]
        return self

    @property
    def text(self) -> str:
        """Convenience property for primary option text."""
        return self.text_str_en or self.text_str_hi or ""


class Answer(BaseModel):
    """Correct answer, if answer key is in scope."""

    correct_options: list[str] = Field(default_factory=list)
    numeric_value: float | None = None
    numeric_range: tuple[float, float] | None = None


class Question(BaseModel):
    """
    A single exam question with universal content nodes, sub-parts, and compat layer.
    """

    id: str
    number: int
    section: str | None = None
    kind: QuestionKind = QuestionKind.SINGLE_CORRECT
    stem: list[ContentNode] = Field(default_factory=list)
    stem_en: list[Block] = Field(default_factory=list)
    stem_hi: list[Block] = Field(default_factory=list)
    stem_text_en: str = ""
    stem_text_hi: str = ""
    options: list[Option] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)
    table_refs: list[str] = Field(default_factory=list)
    original_number: int | None = None
    sequence_index: int = 0
    marks: Marks | float | None = None
    source_pages: list[int] = Field(default_factory=list)

    # Relationships & universal hierarchy
    children: list[Question] = Field(default_factory=list)
    choice_group: str | None = None
    passage_ref: str | None = None
    parent_question: str | None = None
    sub_question_refs: list[str] = Field(default_factory=list)
    answer: AnswerSpec | Answer | None = None
    solution: list[ContentNode] | None = None
    provenance: Provenance = Provenance.EXTRACTED
    confidence: float = 1.0

    @model_validator(mode="after")
    def sync_v1_v2_stems(self) -> Question:
        """Bi-directional sync between v1 plaintext stem and v2 ContentNodes."""
        # Synthesize stem_text from stem if stem exists
        if self.stem:
            en_parts: list[str] = []
            hi_parts: list[str] = []
            for node in self.stem:
                if isinstance(node, TextNode):
                    if "en" in node.texts:
                        en_parts.append(node.texts["en"])
                    if "hi" in node.texts:
                        hi_parts.append(node.texts["hi"])
                elif isinstance(node, MathNode):
                    en_parts.append(node.code)
                    hi_parts.append(node.code)
            if en_parts and not self.stem_text_en:
                self.stem_text_en = " ".join(en_parts).strip()
            if hi_parts and not self.stem_text_hi:
                self.stem_text_hi = " ".join(hi_parts).strip()

        # Synthesize stem from stem_text if stem is empty
        elif self.stem_text_en or self.stem_text_hi:
            texts: dict[str, str] = {}
            if self.stem_text_en:
                texts["en"] = self.stem_text_en
            if self.stem_text_hi:
                texts["hi"] = self.stem_text_hi
            self.stem = [TextNode(texts=texts)]
        return self


class Table(BaseModel):
    """A recognized table (e.g. match-the-column)."""

    id: str
    page: int
    bbox: BBox
    rows: list[list[Cell]] = Field(default_factory=list)
    sources: list[EngineSource] = Field(default_factory=list)
    status: BlockStatus = BlockStatus.TRUSTED
    question_ref: str | None = None


class Passage(BaseModel):
    """Shared passage/stem for multiple questions (JEE/UPSC)."""

    id: str
    nodes: list[ContentNode] = Field(default_factory=list)
    text_en: list[Block] = Field(default_factory=list)
    text_hi: list[Block] = Field(default_factory=list)
    question_refs: list[str] = Field(default_factory=list)


class Figure(BaseModel):
    """A detected figure/diagram with its crop and classification."""

    id: str
    page: int
    bbox: BBox
    crop_path: str | None = None
    format: str = "png"
    classification: FigureClass = FigureClass.UNKNOWN
    scale_class: str = "img-md"
    width_mm: float | None = None
    height_mm: float | None = None
    question_ref: str | None = None
    option_ref: str | None = None
    perceptual_hash: str | None = None
    watermark_residual: float | None = None
    status: BlockStatus = BlockStatus.TRUSTED


# ---------------------------------------------------------------------------
# Page-level metadata & Document Parts
# ---------------------------------------------------------------------------


class PageInfo(BaseModel):
    """Per-page metadata from S0 intake."""

    page_number: int
    dpi: float | None = None
    width_px: int = 0
    height_px: int = 0
    skew_degrees: float = 0.0
    blur_score: float = 0.0
    contrast: float = 0.0
    classification: PageClassification = PageClassification.UNKNOWN
    processing_path: PageProcessingPath = PageProcessingPath.PATH_A
    has_text_layer: bool = False
    text_layer_valid: bool = False
    legacy_fonts: list[str] = Field(default_factory=list)
    watermark_tier: WatermarkTier = WatermarkTier.W0_NONE
    column_count: int = 1
    is_two_page_spread: bool = False
    has_annotation_ink: bool = False
    image_path: str | None = None
    cleaned_image_path: str | None = None


class DocumentPart(BaseModel):
    """Semantic document section / partition."""

    kind: Literal[
        "cover",
        "instructions",
        "section_header",
        "answer_key",
        "solutions",
        "rough_work",
        "omr",
    ]
    pages: list[int] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)


class LanguageInfo(BaseModel):
    """Declared language and script metadata."""

    code: str
    script: str = "Latin"
    direction: Literal["ltr", "rtl"] = "ltr"


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


class Issue(BaseModel):
    """A problem detected during processing."""

    id: str
    stage: str
    page: int | None = None
    element_id: str | None = None
    block_id: str | None = None
    question_id: str | None = None
    severity: IssueSeverity = IssueSeverity.WARNING
    rule: str | None = None
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    candidates: list[str] = Field(default_factory=list)
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
    source_type: str | None = None
    geometry_final: bool = False


class ExamDocument(BaseModel):
    """
    Root document model — universal representation of an exam paper.
    """

    schema_version: int = 2
    source_path: str
    source_hash: str = ""
    metadata: ExamMetadata = Field(default_factory=ExamMetadata)
    languages: list[LanguageInfo] = Field(default_factory=list)
    parts: list[DocumentPart] = Field(default_factory=list)
    pages: list[PageInfo] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    passages: list[Passage] = Field(default_factory=list)

    page_statuses: dict[int, PageStatus] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)

    created_at: datetime | None = None
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
        return {
            p.page_number
            for p in self.pages
            if p.classification == PageClassification.QUESTIONS
        }

    def blocker_issues(self) -> list[Issue]:
        """Return unresolved blocker issues."""
        return [
            i
            for i in self.issues
            if i.severity == IssueSeverity.BLOCKER and not i.resolved
        ]

    def has_blockers(self) -> bool:
        return len(self.blocker_issues()) > 0


# Re-export migration utilities for convenience
from examforge.ir.migrator import load_document, migrate_v1_to_v2  # noqa: E402

__all__ = [
    "Answer",
    "AnswerSpec",
    "BBox",
    "BlankNode",
    "Block",
    "BlockStatus",
    "BlockType",
    "Cell",
    "CodeNode",
    "ContentNode",
    "DocumentPart",
    "EngineSource",
    "ExamDocument",
    "ExamMetadata",
    "Figure",
    "FigureClass",
    "FigureNode",
    "Issue",
    "IssueSeverity",
    "Lang",
    "LanguageInfo",
    "Marks",
    "MatchColumnsNode",
    "MathNode",
    "Option",
    "PageClassification",
    "PageInfo",
    "PageStatus",
    "Passage",
    "Provenance",
    "Question",
    "QuestionKind",
    "RawCropNode",
    "StatementsNode",
    "Table",
    "TableNode",
    "TextNode",
    "WatermarkTier",
    "load_document",
    "migrate_v1_to_v2",
]
