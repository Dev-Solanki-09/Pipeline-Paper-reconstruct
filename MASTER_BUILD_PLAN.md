# ExamForge: Master Build Plan

> **Purpose**: A spoon-fed, phase-by-phase plan to take ExamForge from its current M1 skeleton to a complete, polished, production-ready application. Written so a less capable AI can execute each phase without mistakes.
>
> **Rule**: Complete each phase fully before starting the next. Never skip a verification step. Never mark a phase done until ALL acceptance tests pass.

---

## Current State (What Already Works)

| Component | File | Status |
|-----------|------|--------|
| IR Schema | `src/examforge/ir/schema.py` | ✅ Complete — 408 lines, all Pydantic models |
| Config | `src/examforge/config.py` | ✅ Complete — layered YAML + env + CLI |
| Spec | `src/examforge/spec.py` | ✅ Complete — frozen rules, deterministic hash |
| Orchestrator | `src/examforge/orchestrator/runner.py` | ✅ Complete — sequential run, checkpoints, resume |
| Manifest | `src/examforge/orchestrator/manifest.py` | ✅ Complete — persistent run tracking |
| Stage Base | `src/examforge/stages/base.py` | ✅ Complete — Stage ABC, StageContext, StageResult |
| S0 Intake | `src/examforge/stages/s0_intake.py` | ✅ Complete — PDF open, page classify, render images |
| S9 Package | `src/examforge/stages/s9_package.py` | ✅ Complete — HTML + JSON + report output |
| CLI | `src/examforge/cli.py` | ✅ Complete — execute, resume, inspect |
| HTML Template | `src/examforge/templates/exam.html.j2` | ✅ Complete — bilingual grid, print CSS |
| Default Spec | `spec/default.spec.yaml` | ✅ Complete — 9 rules, 2 modes |
| Tests | `tests/test_schema.py`, `test_runner.py`, `test_config.py` | ✅ 50/50 passing |

**Last E2E run** on the JEE Advanced PDF (30 pages):
- 1 cover, 19 question pages, 6 answer_key, 4 rough_work detected
- 0 questions extracted (expected — no text extraction or segmentation yet)
- HTML output: 6.8 MB (page images embedded as base64)
- All text layers are valid (digital PDF, not scanned)

**What's NOT built yet** (Stages S1–S8, adapters, validators, all the actual intelligence):

```
S1 Normalize       — deskew, orientation, perspective correction
S2 Clean           — watermark removal, furniture stripping, branding
S3 Dual Parse      — OCR engines (PaddleOCR, Tesseract), block extraction
S4 Exam Structure  — question segmentation, numbering, bilingual pairing
S5 Math & Hindi    — formula LaTeX, Hindi normalization, lexicon checks
S6 Figures         — figure detection, cropping, cleaning, assignment
S7 Render          — Jinja2 template rendering with actual question data
S8 Verify & Repair — validation stack, repair loop, review page
```

---

## Phase Index

| Phase | Name | What It Builds | Effort |
|-------|------|----------------|--------|
| **P1** | Text Extraction (S3 lite) | PyMuPDF text blocks → IR Blocks | 3–4 hours |
| **P2** | Question Segmentation (S4 lite) | Regex segmenter → Questions with options | 4–6 hours |
| **P3** | HTML Rendering (S7) | Actual questions in the HTML template | 2–3 hours |
| **P4** | Figure Extraction (S6 lite) | Detect, crop, assign figures to questions | 4–5 hours |
| **P5** | Furniture & Watermark Removal (S2) | Headers, footers, page numbers, branding | 4–5 hours |
| **P6** | Formula Handling (S5 lite) | LaTeX detection, MathJax/KaTeX rendering | 4–5 hours |
| **P7** | Hindi Text Processing (S5b) | NFC normalization, legacy font, lexicon | 3–4 hours |
| **P8** | Verification & Validators (S8) | All 9 spec rules as executable validators | 5–6 hours |
| **P9** | Polish & Edge Cases | Error handling, logging, CLI UX, perf | 3–4 hours |
| **P10** | Testing & Golden Suite | Integration tests, golden file diffs, CI | 4–5 hours |

**Total estimated: 36–47 hours of focused implementation**

---

## Phase 1: Text Extraction (S3 Lite)

### Goal
Extract text blocks from the PDF text layer using PyMuPDF and convert them into `Block` objects in the IR. This is the foundation — every later phase depends on having blocks.

### Prerequisites
- Phase 0 (current state) complete, `pip install -e ".[dev]"` works, 50 tests pass.

### Files to Create

#### File 1: `src/examforge/stages/s3_parse.py`

```python
"""
S3 Parse: Extract text blocks from pages.

For digital PDFs (which is what our JEE PDF is), we use PyMuPDF's
text extraction directly — no OCR needed. For scanned PDFs, this
stage would call PaddleOCR/Tesseract. In M1, we only handle digital.
"""
```

**What this stage must do, step by step:**

1. **Accept** a `StageContext` where `ctx.document.pages` is already populated by S0.
2. **For each page** where `page.has_text_layer and page.text_layer_valid`:
   a. Open the PDF page with `fitz.open(ctx.document.source_path)`.
   b. Call `page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)` to get structured text data.
   c. For each `block` in the result where `block["type"] == 0` (text block):
      - Create a `Block` object with:
        - `id`: `f"b{page_num}_{block_index}"` (must be unique across document)
        - `page`: the 1-indexed page number
        - `bbox`: `BBox(x1=block[0], y1=block[1], x2=block[2], y2=block[3])` (from the block's coordinates)
        - `type`: `BlockType.TEXT` (default)
        - `text`: the block's text content (from `block[4]` in blocks mode, or assembled from spans in dict mode)
        - `lang`: detect using a simple heuristic — if >30% of letter characters are Devanagari (U+0900–U+097F), set to `Lang.HI`, else `Lang.EN`
        - `confidence`: `1.0` (digital text layer = perfect confidence)
        - `sources`: `[EngineSource(engine="pymupdf_text_layer", text=<text>, confidence=1.0)]`
        - `status`: `BlockStatus.TRUSTED`
        - `order`: sequential index within the page (use the block's natural order from PyMuPDF)
   d. Append all blocks to `ctx.document.blocks`.
3. **For pages without valid text layer**: skip for now (OCR comes in a later phase). Add an `Issue` with severity `INFO` saying "Page {N} has no valid text layer, skipping text extraction".
4. **Return** `StageResult` with the updated document, metrics (total blocks extracted, blocks per page), and any issues.

**Exact function signatures:**

```python
class S3Parse(Stage):
    name = "s3_parse"
    
    def run(self, ctx: StageContext) -> StageResult:
        ...
    
    def validate_postconditions(self, result: StageResult) -> list[str]:
        # Must have at least 1 block if there are question pages with valid text
        ...

def _extract_blocks_from_page(
    page: fitz.Page, 
    page_num: int, 
    block_counter: int,
) -> tuple[list[Block], int]:
    """Extract Block objects from a single PDF page.
    
    Args:
        page: PyMuPDF page object
        page_num: 1-indexed page number
        block_counter: running counter for unique block IDs
    
    Returns:
        (list of Blocks, updated block_counter)
    """
    ...

def _detect_block_language(text: str) -> Lang:
    """Detect language of a text block.
    
    Returns Lang.HI if >30% of letter chars are Devanagari, else Lang.EN.
    """
    ...
```

### Wire the Stage into the Pipeline

#### Edit: `src/examforge/cli.py`

In the `_build_stages` function, change:
```python
# BEFORE:
return [S0Intake(), S9Package()]

# AFTER:
from examforge.stages.s3_parse import S3Parse
return [S0Intake(), S3Parse(), S9Package()]
```

### Tests to Write

#### File 2: `tests/test_s3_parse.py`

Write these exact test cases:

```python
class TestExtractBlocksFromPage:
    def test_extracts_text_blocks(self):
        """Open the JEE PDF page 2, extract blocks, verify we get >5 blocks."""
    
    def test_block_ids_are_unique(self):
        """Extract blocks from 3 pages, verify all block IDs are unique."""
    
    def test_block_has_bbox(self):
        """Every extracted block must have a BBox with positive width and height."""
    
    def test_block_text_not_empty(self):
        """Every extracted block must have non-empty text."""
    
    def test_block_confidence_is_one(self):
        """Digital text layer blocks should have confidence=1.0."""

class TestDetectBlockLanguage:
    def test_english_text(self):
        assert _detect_block_language("The mass of the object is 5 kg") == Lang.EN
    
    def test_hindi_text(self):
        assert _detect_block_language("वस्तु का द्रव्यमान 5 kg है") == Lang.HI
    
    def test_mixed_defaults_to_english(self):
        """If <30% Devanagari, classify as English."""
        assert _detect_block_language("Force = 10 N बल") == Lang.EN

class TestS3ParseStage:
    def test_end_to_end_with_sample_pdf(self, sample_pdf_path):
        """Run S0 + S3 on the JEE PDF, verify blocks are populated."""
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")
        # Run pipeline with [S0Intake(), S3Parse()]
        # Assert result.document.blocks is not empty
        # Assert len(result.document.blocks) > 50 (JEE paper has lots of text)
    
    def test_skips_pages_without_text_layer(self):
        """Pages with text_layer_valid=False should produce no blocks."""
```

### Verification Commands

```bash
# Run just the new tests
.venv\Scripts\pytest tests\test_s3_parse.py -v --tb=short

# Run ALL tests to make sure nothing broke
.venv\Scripts\pytest tests\ -v --tb=short

# E2E: run on the JEE PDF and check blocks exist
.venv\Scripts\examforge execute --exam "JEE ADV  MT # 4 NURTURE SANKALP -I BATCH PAPER D-27-07-2025.pdf" --mode fast -v
# Expected: blocks extracted, still 0 questions (segmentation comes in P2)
```

### Acceptance Gate — Do NOT Proceed Until ALL Pass

- [ ] `test_s3_parse.py` — all tests pass
- [ ] All 50 existing tests still pass
- [ ] E2E run shows blocks extracted in the log output (look for "blocks" in metrics)
- [ ] `document.json` in the run directory has a non-empty `blocks` array
- [ ] No Python warnings or deprecation errors in output

---

## Phase 2: Question Segmentation (S4 Lite)

### Goal
Parse the extracted `Block` objects into `Question` objects with stems, options, and numbering. This is where the PDF stops being "a bag of text blocks" and becomes a structured exam.

### Prerequisites
- Phase 1 complete: `document.blocks` is populated after S3.

### Files to Create

#### File 1: `src/examforge/stages/s4_structure.py`

```python
"""
S4 Exam Structure: Segment blocks into Questions.

For a JEE/NEET paper, questions follow predictable patterns:
- Question numbers: "1.", "Q.1", "(1)", "Q1.", etc.
- Options: "(A)", "(B)", "(C)", "(D)" or "(1)", "(2)", "(3)", "(4)"
- Sections: "SECTION - A", "SECTION A", "Part I", etc.

This stage:
1. Sorts blocks by page and reading order (top-to-bottom, left-to-right)
2. Identifies question-start boundaries using regex
3. Groups blocks between question starts into stems + options
4. Handles multi-page questions (stitching across pages)
5. Detects section headers and assigns questions to sections
"""
```

**What this stage must do, step by step:**

1. **Collect all blocks** from question pages only (filter by `page.classification == PageClassification.QUESTIONS`).
2. **Sort blocks** by page number, then by `bbox.y1` (top of block), then by `bbox.x1` (left edge). This gives reading order.
3. **Concatenate all block text** into a single stream, preserving block boundaries.
4. **Scan for question boundaries** using these regex patterns (try each, use the first that matches ≥5 times in the document):
   - Pattern A: `^\s*(\d{1,3})\s*[.):]` — matches "1.", "2)", "3:"
   - Pattern B: `^\s*Q\.?\s*(\d{1,3})` — matches "Q.1", "Q1", "Q 1"
   - Pattern C: `^\s*\((\d{1,3})\)` — matches "(1)", "(2)"
5. **For each question boundary**:
   a. Everything between this boundary and the next is the question's content.
   b. Within the content, scan for option boundaries: `\([A-D]\)` or `\(a\)` through `\(d\)` or `\(1\)` through `\(4\)`.
   c. Text before the first option = stem.
   d. Text after each option marker = that option's text.
6. **Create `Question` objects**:
   ```python
   Question(
       id=f"q{number}",
       number=number,
       kind=QuestionKind.MCQ_SINGLE,  # default; refine later
       stem_en=[Block(...)],  # blocks forming the English stem
       options=[Option(label="A", text_en=[Block(...)]), ...],
       source_pages=[page_num, ...],
   )
   ```
7. **Detect sections**: Look for blocks matching `SECTION\s*[-–]?\s*[A-Za-z0-9]` or `PART\s*[-–]?\s*[IVX0-9]`. Tag questions with their section.
8. **Handle numbering gaps**: If numbers go 1, 2, 3, 5 (missing 4), add an `Issue` with severity `WARNING`: "Question 4 not found — possible OCR or segmentation error".
9. **Detect question kind**:
   - If the question has exactly 4 options → `MCQ_SINGLE`
   - If the stem says "more than one correct" → `MCQ_MULTI`
   - If the stem says "numerical value" or "decimal" → `NUMERIC` (no options expected)
   - If there's a passage reference → `PASSAGE`
10. **Return** updated document with `questions` populated.

**Exact function signatures:**

```python
class S4Structure(Stage):
    name = "s4_structure"
    
    def run(self, ctx: StageContext) -> StageResult: ...
    def validate_postconditions(self, result: StageResult) -> list[str]:
        # Must have ≥1 question if there are question pages with blocks
        ...

def _find_question_pattern(text: str) -> re.Pattern | None:
    """Try multiple question-number patterns and return the best match."""

def _segment_questions(
    blocks: list[Block],
    pattern: re.Pattern,
) -> list[RawQuestion]:
    """Split a sorted block stream into raw question segments."""

@dataclass
class RawQuestion:
    """Intermediate representation before creating Question objects."""
    number: int
    stem_blocks: list[Block]
    option_blocks: dict[str, list[Block]]  # {"A": [...], "B": [...]}
    source_pages: list[int]
    section: str | None = None

def _parse_options(blocks: list[Block]) -> tuple[list[Block], list[Option]]:
    """Separate stem blocks from option blocks.
    
    Returns (stem_blocks, options)
    """

def _detect_question_kind(stem_text: str, options: list[Option]) -> QuestionKind:
    """Determine question type from content patterns."""

def _detect_sections(blocks: list[Block]) -> list[tuple[int, str]]:
    """Find section headers and their block indices.
    
    Returns list of (block_index, section_name).
    """

def _check_numbering_continuity(
    questions: list[Question],
) -> list[Issue]:
    """Check that question numbers form a continuous sequence 1..N.
    
    Returns issues for gaps and duplicates.
    """
```

### Wire the Stage

#### Edit: `src/examforge/cli.py` → `_build_stages()`

```python
from examforge.stages.s4_structure import S4Structure
return [S0Intake(), S3Parse(), S4Structure(), S9Package()]
```

### Tests to Write

#### File: `tests/test_s4_structure.py`

```python
class TestFindQuestionPattern:
    def test_detects_dot_pattern(self):
        """Text with '1. stem 2. stem 3. stem' should match Pattern A."""
    
    def test_detects_q_dot_pattern(self):
        """Text with 'Q.1 stem Q.2 stem' should match Pattern B."""
    
    def test_returns_none_for_no_pattern(self):
        """Random text with no question numbers should return None."""

class TestParseOptions:
    def test_four_options(self):
        """'(A) first (B) second (C) third (D) fourth' → 4 options."""
    
    def test_stem_before_options(self):
        """Text before '(A)' is the stem."""
    
    def test_no_options(self):
        """Text with no option markers → empty options, all text is stem."""

class TestDetectQuestionKind:
    def test_mcq_single_default(self):
        """4 options, no 'more than one' → MCQ_SINGLE."""
    
    def test_mcq_multi(self):
        """Stem contains 'more than one correct answer' → MCQ_MULTI."""
    
    def test_numeric(self):
        """Stem contains 'numerical value' → NUMERIC."""

class TestNumberingContinuity:
    def test_continuous(self):
        """Questions 1,2,3,4,5 → no issues."""
    
    def test_gap(self):
        """Questions 1,2,4,5 → 1 issue about missing Q3."""
    
    def test_duplicate(self):
        """Questions 1,2,2,3 → 1 issue about duplicate Q2."""

class TestS4StructureStage:
    def test_end_to_end(self, sample_pdf_path):
        """Run S0+S3+S4 on JEE PDF → questions extracted."""
        # Assert len(result.document.questions) > 10
        # Assert all questions have non-empty stems
        # Assert most questions have 4 options
    
    def test_questions_have_source_pages(self):
        """Every question must reference at least one source page."""
    
    def test_no_duplicate_question_numbers(self):
        """No two questions should have the same number."""
```

### Verification Commands

```bash
.venv\Scripts\pytest tests\test_s4_structure.py -v --tb=short
.venv\Scripts\pytest tests\ -v --tb=short
.venv\Scripts\examforge execute --exam "<JEE_PDF>" --mode fast -v
# Expected output: "Questions: N" where N > 0
```

### Acceptance Gate

- [ ] All new tests pass
- [ ] All 50+ existing tests pass
- [ ] E2E run shows `Questions: N` where N > 10
- [ ] `document.json` has a non-empty `questions` array
- [ ] Each question has `stem_en` with text and `options` with labels A–D
- [ ] Numbering continuity check runs (even if it finds gaps — that's OK for now)

---

## Phase 3: HTML Rendering with Questions (S7)

### Goal
The HTML template already exists but only shows page previews. Update it so that when questions exist, they render as properly formatted question-and-options in the HTML.

### Prerequisites
- Phase 2 complete: `document.questions` is populated.

### Files to Edit

#### Edit 1: `src/examforge/templates/exam.html.j2`

The template already has the question rendering code (the `{% for question in questions %}` block), but there are potential issues:

1. **The stem blocks**: Questions store stems as lists of `Block` objects with a `.text` field. The template accesses `question.stem_en` which should be a list of Blocks. Verify the template iteration works: `{% for block in question.stem_en %}{{ block.text | e }}{% endfor %}`.

2. **Options**: Similarly, `option.text_en` is a list of Blocks.

3. **The fallback**: When questions ARE present, the "Page Previews" section should NOT show. The existing `{% if not questions %}` guard handles this.

**Specific changes to make:**

a. Add a "Questions" header before the questions section.
b. Add section headers between sections (if `question.section` changes).
c. Add question kind badge (MCQ, Numeric, etc.).
d. Add marking scheme display if available.
e. Make the question number a link anchor (`#q1`, `#q2`, etc.) — already done via `id="q{{ question.number }}"`.
f. Add a table of contents at the top linking to each question.

#### Edit 2: Improve the stem/option rendering

The IR schema stores `stem_en` as `list[Block]`. Verify the Jinja2 template can iterate over this correctly. If `stem_en` is empty (which it might be in M1 since we're building stem as text, not block references), update the Question model or the S4 stage to store stems as text strings directly.

> **IMPORTANT DECISION**: For simplicity in M1, store the stem and option text as plain strings on the Question/Option objects rather than block references. Add fields:
> - `Question.stem_text_en: str = ""`
> - `Question.stem_text_hi: str = ""`
> - `Option.text_str_en: str = ""`
> - `Option.text_str_hi: str = ""`

This avoids the complexity of block-reference rendering in the template.

#### Edit 3: `src/examforge/ir/schema.py`

Add the convenience text fields to `Question` and `Option`:
```python
class Option(BaseModel):
    label: str
    text_en: list[Block] = Field(default_factory=list)
    text_hi: list[Block] = Field(default_factory=list)
    text_str_en: str = ""    # ADD THIS
    text_str_hi: str = ""    # ADD THIS
    figure_ref: str | None = None

class Question(BaseModel):
    # ... existing fields ...
    stem_text_en: str = ""   # ADD THIS
    stem_text_hi: str = ""   # ADD THIS
```

#### Edit 4: Update the Jinja2 template

Replace the block-iteration stem rendering with simple text output:
```html
<!-- In the English stem -->
<span class="q-stem">{{ question.stem_text_en | e }}</span>

<!-- In options -->
<span>{{ option.text_str_en | e }}</span>
```

### Tests to Write

#### File: `tests/test_rendering.py`

```python
class TestHTMLRendering:
    def test_questions_appear_in_html(self, sample_pdf_path):
        """Run full pipeline, check HTML contains question text."""
        # Parse HTML output
        # Assert "1." appears in the HTML
        # Assert "(A)" appears in the HTML
    
    def test_no_page_previews_when_questions_exist(self):
        """When questions > 0, page preview section should not appear."""
    
    def test_html_is_valid(self):
        """Output HTML should have matching open/close tags."""
    
    def test_metadata_in_html_head(self):
        """Check that spec hash and exam name are in meta tags."""
```

### Verification Commands

```bash
.venv\Scripts\pytest tests\test_rendering.py -v --tb=short
.venv\Scripts\pytest tests\ -v --tb=short
.venv\Scripts\examforge execute --exam "<JEE_PDF>" --mode fast --debug -v
# Open the output.html in a browser and visually verify questions render
```

### Acceptance Gate

- [ ] All tests pass
- [ ] HTML output contains readable question text with numbered questions
- [ ] Options (A), (B), (C), (D) are visible and formatted
- [ ] Opening the HTML in a browser shows a clean, readable exam paper
- [ ] The page preview fallback still works when there are 0 questions

---

## Phase 4: Figure Extraction (S6 Lite)

### Goal
Detect figures/diagrams in the PDF, crop them cleanly, and assign them to the correct questions.

### Prerequisites
- Phase 2 complete: questions exist.

### Files to Create

#### File 1: `src/examforge/stages/s6_figures.py`

**Step by step:**

1. **For each question page**, get embedded images using `page.get_images(full=True)`.
2. **For each image**:
   a. Extract the image using `fitz.Pixmap(doc, xref)`.
   b. Get the image's position on the page using `page.get_image_rects(xref)`.
   c. Create a `Figure` object:
      ```python
      Figure(
          id=f"fig_{page_num}_{img_idx}",
          page=page_num,
          bbox=BBox(x1=rect.x0, y1=rect.y0, x2=rect.x1, y2=rect.y1),
          classification=FigureClass.DIAGRAM,  # default
      )
      ```
   d. Save the cropped image to `ctx.stage_dir / "figures" / f"fig_{page_num}_{img_idx}.png"`.
   e. Set `figure.crop_path` to the relative path.
3. **Also detect non-text regions** that aren't images:
   a. Get all text block bboxes on the page.
   b. Get all image bboxes.
   c. Find large "gaps" in the page that aren't covered by text or images — these may be diagrams drawn with PDF vector commands.
   d. For these, render a crop from the page image (already saved in S0).
4. **Classify figures**: 
   - Small images (<50×50 px) → likely bullets or icons, skip
   - Images with aspect ratio > 5:1 → likely decorative lines, skip
   - QR codes → classify as `FigureClass.QR_CODE`, skip
   - Everything else → `FigureClass.DIAGRAM`
5. **Assign figures to questions**:
   a. For each figure, find the nearest question by page number and vertical position.
   b. A figure belongs to a question if it's on the same page and its bbox.y1 falls between the question's start and the next question's start.
   c. Set `figure.question_ref = question.id`.
   d. Add the figure ID to `question.figure_refs`.
6. **Add figures to document**: `ctx.document.figures = figures`.

**Exact function signatures:**

```python
class S6Figures(Stage):
    name = "s6_figures"
    def run(self, ctx: StageContext) -> StageResult: ...

def _extract_embedded_images(
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    output_dir: Path,
) -> list[Figure]:
    """Extract embedded images from a PDF page."""

def _classify_figure(
    width: int, height: int, image_data: bytes | None = None,
) -> FigureClass | None:
    """Classify a figure. Returns None if it should be skipped."""

def _assign_figures_to_questions(
    figures: list[Figure],
    questions: list[Question],
) -> None:
    """Assign each figure to its nearest question (mutates both)."""
```

### Wire the Stage

```python
# cli.py → _build_stages()
from examforge.stages.s6_figures import S6Figures
return [S0Intake(), S3Parse(), S4Structure(), S6Figures(), S9Package()]
```

### Tests to Write

#### File: `tests/test_s6_figures.py`

```python
class TestClassifyFigure:
    def test_skip_tiny_images(self):
        """Images smaller than 50x50 should return None."""
    
    def test_skip_decorative_lines(self):
        """Very wide, short images (aspect > 5:1) should return None."""
    
    def test_normal_diagram(self):
        """300x200 image → FigureClass.DIAGRAM."""

class TestAssignFiguresToQuestions:
    def test_figure_assigned_to_nearest_question(self):
        """Figure on page 5 at y=400 should be assigned to the question
        whose bbox spans that y coordinate."""
    
    def test_figure_on_different_page(self):
        """A figure on page 3 should not be assigned to a question on page 5."""

class TestS6FiguresStage:
    def test_end_to_end(self, sample_pdf_path):
        """Run S0+S3+S4+S6 on JEE PDF → some figures extracted."""
        # JEE papers typically have diagrams
```

### Acceptance Gate

- [ ] All tests pass
- [ ] E2E run shows figure count > 0 in metrics
- [ ] Figure crop PNGs exist in the run directory under `stages/s6_figures/figures/`
- [ ] HTML output embeds figure images (visible when opened in browser)
- [ ] Figures are assigned to questions (check `document.json` → `questions[].figure_refs`)

---

## Phase 5: Furniture & Watermark Removal (S2)

### Goal
Identify and strip headers, footers, page numbers, branding text, logos, and watermarks so the final HTML contains only question content.

### Prerequisites
- Phase 1 complete: blocks exist.

### Files to Create

#### File 1: `src/examforge/stages/s2_clean.py`

**What this stage must do:**

1. **Detect repeating furniture**: 
   a. For each block, compute its "normalized position" = `(bbox.y1 / page_height, bbox.x1 / page_width)`.
   b. Group blocks across pages by normalized position (within ±2% tolerance).
   c. Blocks that appear at the same position on ≥80% of question pages are furniture candidates.
   d. Further filter: if the text matches known furniture patterns (page numbers like "1", "2", "Page 1"; headers with exam name; footers with "Space for Rough Work"), mark as furniture.
2. **Mark furniture blocks** as `status=BlockStatus.DROPPED`, `drop_reason="Repeating furniture at position (x, y)"`, `type=BlockType.HEADER/FOOTER/PAGE_NUMBER`.
3. **Detect branding**: 
   - Text matching patterns: URLs (`http://`, `www.`), phone numbers (`\d{10}`), coaching institute names (configurable list or learned from the specific paper).
   - Mark as `BlockStatus.DROPPED`, `type=BlockType.LOGO` or `BlockType.URL`.
4. **Detect watermark text in text layer** (for digital PDFs):
   - Text with very large font size (>40pt) and rotated ~45° is likely a watermark.
   - Text that appears on every page with the same content.
   - Mark as `BlockStatus.DROPPED`, `type=BlockType.WATERMARK`.
5. **Log every drop** with full evidence: block ID, text content, reason, page number.
6. **Guarantee G2**: Content is dropped ONLY with positive evidence. If uncertain, flag as an Issue but do NOT drop.

**Exact function signatures:**

```python
class S2Clean(Stage):
    name = "s2_clean"
    def run(self, ctx: StageContext) -> StageResult: ...
    def validate_postconditions(self, result: StageResult) -> list[str]:
        # No block should be dropped without a drop_reason
        ...

def _find_repeating_furniture(
    blocks: list[Block],
    pages: list[PageInfo],
    threshold: float = 0.8,
    position_tolerance: float = 0.02,
) -> list[str]:
    """Find block IDs that appear at the same position on ≥threshold of pages.
    
    Returns list of block IDs to mark as furniture.
    """

def _detect_page_numbers(blocks: list[Block]) -> list[str]:
    """Find blocks that are standalone numbers matching page sequence."""

def _detect_branding(blocks: list[Block]) -> list[str]:
    """Find blocks containing URLs, phone numbers, or branding text."""

def _detect_watermark_text(
    blocks: list[Block], pages: list[PageInfo],
) -> list[str]:
    """Find text-layer watermarks (large, rotated, repeating)."""
```

### Important: Stage Ordering

S2 runs BEFORE S3 Parse in the pipeline. Update `_build_stages()`:
```python
return [S0Intake(), S2Clean(), S3Parse(), S4Structure(), S6Figures(), S9Package()]
```

Wait — actually S2 needs blocks to identify furniture, but S3 creates the blocks. This is a chicken-and-egg problem.

**Resolution**: S2 should operate on the raw PDF objects (font size, position, rotation) directly from PyMuPDF, NOT on the IR blocks. S3 then creates blocks and marks the ones that S2 flagged as furniture.

**Alternative (simpler for M1)**: Run S3 first to create blocks, then run S2 to filter them:
```python
return [S0Intake(), S3Parse(), S2Clean(), S4Structure(), S6Figures(), S9Package()]
```

This is fine for M1. S4 only looks at non-dropped blocks, so furniture doesn't pollute question segmentation.

### Tests

#### File: `tests/test_s2_clean.py`

```python
class TestFindRepeatingFurniture:
    def test_detects_header(self):
        """A block at y=0.02 on 90% of pages → detected as furniture."""
    
    def test_does_not_drop_unique_blocks(self):
        """A block appearing on only 1 page → NOT furniture."""
    
    def test_position_tolerance(self):
        """Blocks at y=0.020 and y=0.021 should be grouped together."""

class TestDetectPageNumbers:
    def test_sequential_numbers(self):
        """Blocks '1', '2', '3' at bottom of consecutive pages → page numbers."""
    
    def test_non_sequential_not_detected(self):
        """Blocks '5', '2', '8' → not page numbers."""

class TestDetectBranding:
    def test_url_detected(self):
        """Block containing 'www.example.com' → branding."""
    
    def test_phone_number_detected(self):
        """Block containing '9876543210' → branding."""
    
    def test_normal_text_not_branding(self):
        """Block with question text → NOT branding."""

class TestS2CleanStage:
    def test_dropped_blocks_have_reasons(self):
        """Every dropped block must have a non-empty drop_reason."""
    
    def test_end_to_end(self, sample_pdf_path):
        """Run pipeline, verify some blocks are dropped."""
```

### Acceptance Gate

- [ ] All tests pass
- [ ] E2E run shows some blocks with `status: dropped` in `document.json`
- [ ] Every dropped block has a `drop_reason` (Guarantee G2)
- [ ] Question text blocks are NOT dropped
- [ ] Headers/footers/page numbers are dropped
- [ ] Pipeline log shows "Dropped N blocks as furniture" or similar

---

## Phase 6: Formula Handling (S5 Lite)

### Goal
Detect mathematical formulas in the text, preserve them as LaTeX, and render them using KaTeX or MathJax in the HTML output.

### Prerequisites
- Phase 2 complete: questions with stem text exist.

### Files to Create

#### File 1: `src/examforge/stages/s5_math.py`

**Step by step:**

1. **Detect formulas in text blocks**: PyMuPDF's text layer for digital PDFs preserves some mathematical symbols (√, ∫, Σ, etc.) but loses formatting (fractions, superscripts, subscripts). For digital PDFs:
   a. Look for blocks where the font contains "Math", "Symbol", "CMMI", "CMSY", or "CMEX" (TeX math fonts).
   b. Look for text containing mathematical Unicode: superscript/subscript digits (²³₁₂), operators (±×÷≤≥≠∞), Greek letters (α β γ), roots (√∛), integrals (∫∬), etc.
   c. Mark these blocks as `type=BlockType.FORMULA`.
2. **For detected formula blocks**, attempt basic LaTeX conversion:
   a. Superscripts: `x²` → `x^{2}`
   b. Subscripts: `x₁` → `x_{1}` 
   c. Greek: `α` → `\alpha`, `β` → `\beta`, etc.
   d. Operators: `×` → `\times`, `÷` → `\div`, `√` → `\sqrt{}`
   e. Store as `block.latex = "<converted>"`.
3. **For complex formulas** (fractions, integrals, matrices) that can't be auto-converted from Unicode: leave `block.latex = None` and flag an `Issue` with `severity=WARNING`.
4. **Update the HTML template** to use KaTeX for rendering:
   a. Add KaTeX CSS and JS to the `<head>` (CDN links, or inline for single-file).
   b. Wrap formula text in `<span class="math">` tags.
   c. Add a script that auto-renders all `.math` spans using KaTeX.

**Function signatures:**

```python
class S5Math(Stage):
    name = "s5_math"
    def run(self, ctx: StageContext) -> StageResult: ...

def _detect_math_blocks(blocks: list[Block]) -> list[str]:
    """Find block IDs that contain mathematical content.
    Returns list of block IDs to mark as FORMULA."""

def _unicode_to_latex(text: str) -> str:
    """Convert Unicode math symbols to LaTeX.
    E.g., 'x² + y²' → 'x^{2} + y^{2}'"""

UNICODE_TO_LATEX_MAP: dict[str, str] = {
    "²": "^{2}", "³": "^{3}", "¹": "^{1}",
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma",
    "θ": r"\theta", "π": r"\pi", "Σ": r"\Sigma",
    "√": r"\sqrt", "∞": r"\infty",
    "×": r"\times", "÷": r"\div",
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq",
    "°": r"^{\circ}",
    # ... extend as needed
}
```

### Tests

#### File: `tests/test_s5_math.py`

```python
class TestUnicodeToLatex:
    def test_superscripts(self):
        assert _unicode_to_latex("x²") == r"x^{2}"
    
    def test_greek(self):
        assert _unicode_to_latex("sin θ") == r"sin \theta"
    
    def test_mixed(self):
        assert _unicode_to_latex("E = mc²") == r"E = mc^{2}"
    
    def test_plain_text_unchanged(self):
        assert _unicode_to_latex("hello world") == "hello world"

class TestDetectMathBlocks:
    def test_detects_formula(self):
        """Block with '∫ x² dx' should be detected as math."""
    
    def test_plain_text_not_math(self):
        """Block with 'The answer is 42' should NOT be math."""
```

### Acceptance Gate

- [ ] All tests pass
- [ ] Formulas with Greek letters, superscripts, subscripts render in HTML
- [ ] KaTeX script is included in the HTML `<head>`
- [ ] Plain text is not incorrectly marked as formulas
- [ ] Opening the HTML shows properly rendered math (fractions, powers, etc.)

---

## Phase 7: Hindi Text Processing (S5b)

### Goal
Handle Hindi/Devanagari text properly: NFC normalization, legacy font detection (already in S0), and basic lexicon checking.

### Prerequisites
- Phase 1 complete: blocks exist with language detection.

### Files to Create

#### File 1: `src/examforge/stages/s5_hindi.py`

**Step by step:**

1. **NFC Normalize** all Hindi text blocks: `text = unicodedata.normalize("NFC", text)`.
2. **Fix common OCR errors in Devanagari**:
   - Nukta confusion: sometimes `क` is used where `क़` is needed.
   - Danda vs pipe: `।` (U+0964 DEVANAGARI DANDA) vs `|` (U+007C VERTICAL LINE) — always use danda.
   - Zero-width joiner cleanup: remove spurious ZWJ/ZWNJ characters.
3. **Digit script preservation**: If the source uses Devanagari digits (०१२), preserve them. If it uses Arabic digits (012), keep those. Don't mix.
4. **Basic lexicon check** (optional in M1):
   - Load a small Hindi word list (1000 common science terms).
   - Flag words not in the lexicon as potential OCR errors.
   - This is an INFO-level issue, not a blocker.
5. **Bilingual pairing hint**: For each Hindi block, try to find a nearby English block with similar numbers/units. Store this as a cross-reference for S4 to use in bilingual pairing.

**This is a simpler stage.** The key deliverable is NFC normalization and danda fixing — these are deterministic and can't go wrong.

### Tests

```python
class TestHindiNormalization:
    def test_nfc(self):
        """Decomposed Devanagari → NFC composed form."""
    
    def test_danda_fix(self):
        """'|' at end of Hindi sentence → '।'"""
    
    def test_zwj_cleanup(self):
        """Spurious ZWJ removed from text."""
    
    def test_preserves_devanagari_digits(self):
        """'१२३' stays as '१२३', not converted to '123'."""
```

### Acceptance Gate

- [ ] Hindi text in the HTML is NFC-normalized
- [ ] Dandas are correct (।, not |)
- [ ] No ZWJ/ZWNJ corruption
- [ ] Digit scripts are preserved

---

## Phase 8: Verification & Validators (S8)

### Goal
Implement the 9 spec rules as executable validator functions, and build S8 to run them all.

### Prerequisites
- Phases 1–7 complete.

### Files to Create

#### File 1: `src/examforge/stages/s8_verify.py`

The verification stage runs all validators from the spec and produces issues.

```python
class S8Verify(Stage):
    name = "s8_verify"
    
    def run(self, ctx: StageContext) -> StageResult:
        issues = []
        for rule_name, rule in ctx.spec.rules.items():
            validator = VALIDATOR_REGISTRY.get(rule.check)
            if validator is None:
                issues.append(Issue(
                    id=f"s8_no_validator_{rule_name}",
                    stage=self.name,
                    severity=IssueSeverity.WARNING,
                    message=f"No validator for rule {rule_name} (check={rule.check})",
                ))
                continue
            rule_issues = validator(ctx.document, rule)
            for issue in rule_issues:
                issue.rule = rule_name
                issue.severity = IssueSeverity(rule.severity.value)
            issues.extend(rule_issues)
        return StageResult(document=ctx.document, issues=issues)
```

#### Files 2–10: One validator per rule

Create each in `src/examforge/validators/`:

| File | Rule | What It Checks |
|------|------|----------------|
| `r01_no_furniture.py` | R01 | No blocks with type HEADER/FOOTER/PAGE_NUMBER have status != DROPPED |
| `r02_no_branding.py` | R02 | No blocks with type LOGO/URL/QR_CODE have status != DROPPED |
| `r03_no_watermark.py` | R03 | No blocks with type WATERMARK have status != DROPPED |
| `r04_continuous.py` | R04 | HTML has no `<div class="page-break">` or page-wrapper elements |
| `r05_bilingual.py` | R05 | Every question has both `stem_text_en` and `stem_text_hi` (or is flagged) |
| `r06_complete.py` | R06 | Question numbers form a continuous sequence 1..N |
| `r07_formulas.py` | R07 | Every formula block has valid LaTeX that round-trips |
| `r08_figures.py` | R08 | Every question referencing a figure has a non-empty `figure_refs` |
| `r09_unicode.py` | R09 | All Hindi text is NFC-normalized |

Each validator is a function with this signature:

```python
def validate(document: ExamDocument, rule: Rule) -> list[Issue]:
    """Run the check and return a list of issues found."""
```

#### File 11: `src/examforge/validators/registry.py`

```python
VALIDATOR_REGISTRY: dict[str, Callable] = {
    "no_headers_footers_page_numbers": r01_no_furniture.validate,
    "no_brand_text_or_logo": r02_no_branding.validate,
    "watermark_residual": r03_no_watermark.validate,
    "no_page_wrappers_or_breaks": r04_continuous.validate,
    "en_hi_pairs_complete": r05_bilingual.validate,
    "numbering_continuity": r06_complete.validate,
    "formula_roundtrip": r07_formulas.validate,
    "figure_clean_border_and_present": r08_figures.validate,
    "devanagari_nfc_and_lexicon": r09_unicode.validate,
}
```

### Tests

Write one test file per validator (`tests/test_validators.py`) with:
- A "pass" case: clean document → no issues
- A "fail" case: document with a known violation → exactly 1 issue of the right severity
- Edge cases specific to each rule

### Acceptance Gate

- [ ] All 9 validators implemented and registered
- [ ] S8 runs all validators and produces issues
- [ ] Each validator has pass/fail tests
- [ ] E2E run shows issues in the report (some rules will fail — that's expected)
- [ ] Exit code reflects the severity (blockers → exit 30)

---

## Phase 9: Polish & Edge Cases

### Goal
Harden the application: error handling, logging, CLI UX, performance, and edge cases.

### Tasks (do each one and test):

1. **Error handling in every stage**: Wrap all file I/O in try/except. Never crash on a single bad page — log an Issue and continue.

2. **Progress reporting**: Add `tqdm` progress bars for page processing in S0 and S3. Add `tqdm` to `pyproject.toml` dependencies.

3. **CLI improvements**:
   - `examforge execute` should print the HTML output path at the end.
   - `examforge inspect` should show a formatted table, not raw JSON.
   - Add `--output-dir` flag to specify where to save results (default: `./runs`).
   - Add `--quiet` flag to suppress all output except errors.

4. **Performance**: 
   - Page rendering in S0 takes ~2s/page × 30 pages = 60s. Add `--max-pages N` support (already in CLI, wire to S0).
   - Cache the PDF document object instead of re-opening it in S3 and S6.

5. **Logging**:
   - All log messages use ASCII (already fixed).
   - Add `--log-file` flag to write logs to a file.
   - Stage timing is already in metrics — add it to the log output.

6. **Edge cases**:
   - Empty PDF (0 pages) → clean error message, exit 30.
   - Corrupted PDF → catch `fitz.FileDataError`, clean error, exit 30.
   - PDF with password → detect and error with message.
   - Very large PDF (>100 pages) → warn but proceed.

### Tests

```python
class TestEdgeCases:
    def test_empty_pdf(self, tmp_path):
        """An empty file → FileNotFoundError or clean error."""
    
    def test_corrupted_pdf(self, tmp_path):
        """Random bytes → clean error, not a crash."""
    
    def test_non_pdf_file(self, tmp_path):
        """A .txt file → clean error message."""
```

### Acceptance Gate

- [ ] Pipeline never crashes with a Python traceback on bad input
- [ ] Every error produces a human-readable message
- [ ] `--help` output is clear and complete
- [ ] Progress bars show during processing
- [ ] All 70+ tests pass

---

## Phase 10: Testing & Golden Suite

### Goal
Build a comprehensive test suite that prevents regressions and validates the full pipeline.

### Tasks

1. **Golden file test**:
   - Run the pipeline on the JEE PDF.
   - Save the `report.json` as `tests/golden/jee_report.json`.
   - Write a test that re-runs the pipeline and compares the report structure (not byte-exact, but structural: same page count, same classification, same question count ±2).

2. **Snapshot test for HTML**:
   - Save key sections of the HTML (the page summary table, the first 3 questions) as golden snapshots.
   - Test that re-runs produce structurally equivalent HTML.

3. **Regression test for classification**:
   - Page 1 should always be COVER.
   - Pages 27–30 should always be ROUGH_WORK.
   - Pages 2, 4, 5, 6 should be QUESTIONS.

4. **Fault injection tests** (from Section 7 of the architecture):
   - Take a correct Question object and delete option (C) → R06 validator should catch it.
   - Add a dropped block with no `drop_reason` → pipeline postcondition should fail.
   - Inject a block with `type=WATERMARK, status=TRUSTED` → R03 should flag it.

5. **Coverage target**: Run `pytest --cov=examforge` and ensure ≥80% coverage.

6. **CI-ready script**: Create a `scripts/test.sh` (or `.ps1` for Windows):
   ```
   .venv\Scripts\pytest tests\ -v --tb=short --cov=examforge --cov-report=term-missing
   ```

### Files to Create

```
tests/
  golden/
    jee_report.json          # Expected report structure
  test_golden.py             # Golden file comparison tests
  test_fault_injection.py    # Fault injection tests
  test_edge_cases.py         # Edge case tests
```

### Acceptance Gate — FINAL

- [ ] ALL tests pass (target: 100+ tests)
- [ ] Coverage ≥ 80%
- [ ] E2E run on JEE PDF produces:
  - Page classification: correct (1 cover, 19 questions, 6 answer_key, 4 rough_work)
  - Questions extracted: >10
  - Figures extracted: >0
  - HTML opens in browser and looks like a real exam paper
  - Report JSON has all expected fields
- [ ] `examforge --help` shows clean output
- [ ] `examforge execute --exam <pdf>` works end-to-end
- [ ] `examforge resume --run-id <id>` resumes correctly
- [ ] `examforge inspect --run-id <id>` shows formatted output
- [ ] No deprecation warnings
- [ ] No Unicode errors on Windows

---

## Appendix A: Full Pipeline Stage Order

After all phases are complete, `_build_stages()` returns:

```python
def _build_stages(config):
    from examforge.stages.s0_intake import S0Intake
    from examforge.stages.s2_clean import S2Clean       # P5
    from examforge.stages.s3_parse import S3Parse        # P1
    from examforge.stages.s4_structure import S4Structure # P2
    from examforge.stages.s5_hindi import S5Hindi         # P7
    from examforge.stages.s5_math import S5Math           # P6
    from examforge.stages.s6_figures import S6Figures      # P4
    from examforge.stages.s7_render import S7Render        # P3 (if separate)
    from examforge.stages.s8_verify import S8Verify        # P8
    from examforge.stages.s9_package import S9Package

    return [
        S0Intake(),       # Open PDF, classify pages, render images
        S3Parse(),        # Extract text blocks from text layer
        S2Clean(),        # Strip furniture, branding, watermarks
        S5Hindi(),        # NFC normalize Hindi, fix dandas
        S5Math(),         # Detect and convert math formulas
        S4Structure(),    # Segment blocks into questions
        S6Figures(),      # Extract and assign figures
        S8Verify(),       # Run all 9 spec validators
        S9Package(),      # Generate HTML + JSON + report
    ]
```

> **Note**: S1 Normalize (deskew, orientation) and S7 Render (as a separate stage) are deferred. For digital PDFs they are not needed. S9 Package already handles the Jinja2 rendering.

## Appendix B: File Tree After All Phases

```
pipeline/
├── pyproject.toml
├── README.md
├── examforge.yaml
├── .gitignore
├── spec/
│   └── default.spec.yaml
├── src/examforge/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── spec.py
│   ├── ir/
│   │   ├── __init__.py
│   │   └── schema.py
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── manifest.py
│   │   └── runner.py
│   ├── stages/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── s0_intake.py
│   │   ├── s2_clean.py
│   │   ├── s3_parse.py
│   │   ├── s4_structure.py
│   │   ├── s5_hindi.py
│   │   ├── s5_math.py
│   │   ├── s6_figures.py
│   │   ├── s8_verify.py
│   │   └── s9_package.py
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── r01_no_furniture.py
│   │   ├── r02_no_branding.py
│   │   ├── r03_no_watermark.py
│   │   ├── r04_continuous.py
│   │   ├── r05_bilingual.py
│   │   ├── r06_complete.py
│   │   ├── r07_formulas.py
│   │   ├── r08_figures.py
│   │   └── r09_unicode.py
│   └── templates/
│       └── exam.html.j2
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_runner.py
│   ├── test_schema.py
│   ├── test_s2_clean.py
│   ├── test_s3_parse.py
│   ├── test_s4_structure.py
│   ├── test_s5_math.py
│   ├── test_s5_hindi.py
│   ├── test_s6_figures.py
│   ├── test_s8_verify.py
│   ├── test_rendering.py
│   ├── test_validators.py
│   ├── test_edge_cases.py
│   ├── test_fault_injection.py
│   ├── test_golden.py
│   └── golden/
│       └── jee_report.json
└── runs/                          # git-ignored
```

## Appendix C: Rules for the Implementing AI

> [!CAUTION]
> **Follow these rules EXACTLY. Breaking any of them will cause bugs.**

1. **Never skip tests.** After creating ANY file, run `pytest tests\ -v --tb=short`. If any test fails, fix it before proceeding.
2. **Never modify `schema.py` without running `test_schema.py` afterwards.** The IR schema is the contract — breaking it breaks everything.
3. **Always run E2E** after completing a phase: `examforge execute --exam <pdf> --mode fast -v`. Check the output.
4. **Never use Unicode symbols in log messages or CLI output.** Windows cp1252 will break. Use ASCII: `[OK]`, `[FAIL]`, `[WARN]`, `--`.
5. **Never use `import fitz`** — use `import pymupdf as fitz` or add a deprecation suppression. The `fitz` alias is deprecated.
6. **Every dropped block MUST have a `drop_reason`.** This is Guarantee G2. Test for it.
7. **Every new stage must be wired into `_build_stages()` in `cli.py`** in the correct position.
8. **Every new stage must have `validate_postconditions()`** that checks meaningful invariants.
9. **Use `Path` objects, never string paths.** Cross-platform compatibility.
10. **All file writes use `encoding="utf-8"`.** Never rely on system default encoding.
11. **Test file:** Every new source file `src/examforge/X.py` gets a corresponding `tests/test_X.py`.
12. **Do not install new dependencies** without adding them to `pyproject.toml` under `[project.dependencies]`.
13. **The virtual environment is at `.venv\`**. Always use `.venv\Scripts\pytest`, `.venv\Scripts\examforge`, etc.
14. **Working directory is `c:\Users\D.Solanki\pipeline\`**. All paths are relative to this.
15. **The sample PDF is at**: `c:\Users\D.Solanki\pipeline\JEE ADV  MT # 4 NURTURE SANKALP -I BATCH PAPER D-27-07-2025.pdf`
