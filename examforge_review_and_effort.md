# ExamForge: Architecture Review, Effort Estimate & Polished Build Plan

## Part 1 — Review & Critique

### What's strong

| Area | Why it works |
|---|---|
| **Fail-closed philosophy (G1)** | The right default — a missed error is worse than a blocked run |
| **Dual-engine OCR with alignment** | The single highest-ROI accuracy technique for OCR pipelines |
| **Watermark ladder (S2)** | Correct progression: cheap/safe → expensive/risky, with per-page winner selection |
| **Content-addressed artifacts** | Enables incremental re-runs without rebuilding everything |
| **Layered verification (L1–L8)** | Cheap structural checks first, expensive visual QA last — correct ordering |
| **Failure-mode catalogue** | Unusually thorough; most architecture docs skip this entirely |
| **IR schema** | Provenance tracking (engine, confidence, status) is exactly right for a multi-engine system |
| **"Learn only through reviewed changes"** | Prevents threshold drift and makes regressions traceable |
| **Exit codes for automation** | Small detail, big operational value |

---

### 10 Architectural concerns

#### 1. No page-level failure policy

> *"A violated post-condition stops the run."*

If page 8 of 15 fails S3, does the entire run stop? The doc mentions "per-page parallelism" but never defines how page-level failures propagate. Need:
- Per-page status enum: `pending | running | done | failed | skipped`
- A configurable policy: `fail_fast` (stop all), `fail_page` (skip page, continue others), `fail_warn` (continue, mark degraded)
- The manifest must record which pages succeeded and which didn't

#### 2. The "Agent" is a black box

Section 8 references four agent roles (Adjudicator, Repairer, Planner, Reviewer) but never specifies:
- **Which LLM?** GPT-4o? Gemini? Local model?
- **What happens when the API is down?** No fallback defined
- **Cost model?** A single exam paper with 200 questions could generate hundreds of agent calls
- **Latency?** LLM calls are 1–10s each; this dominates pipeline runtime

**Recommendation:** Define the agent as an interface with a concrete default (e.g., Gemini 2.0 Flash via API) and a "no-agent" mode where all disputes go to human review. Build the pipeline to work without an agent first.

#### 3. MCP is over-weighted

> *"Bulk work should prefer direct library or API calls"* and *"MCP is valuable when an agent chooses tools; deterministic bulk work does not need it."*

The doc contradicts itself. If bulk work (95%+ of processing) doesn't need MCP, then MCP is an optional debugging interface, not a core architectural element. Building dual-surface adapters (direct + MCP) per engine doubles the adapter maintenance cost.

**Recommendation:** Drop MCP from v1 entirely. Add it as an optional debug layer in v2 if interactive agent-driven exploration proves valuable.

#### 4. Browser is a serialization bottleneck

Three subsystems need a browser: formula pre-rendering (S5), HTML rendering (S7), and render round-trip verification (L5). "One reused browser session" is a single point of failure and a serialization point.

**Needs:**
- Browser pool with configurable concurrency (2–4 instances)
- Crash recovery (Playwright handles this natively)
- Explicit dependency: Chromium must be installed (Playwright can auto-install it)
- Fallback: if browser is unavailable, formulas degrade to `<img>` tags from an external renderer

#### 5. Artifact store is under-specified

"SHA-256 of content plus parameters plus engine version" is a one-liner that hides weeks of implementation:
- Directory structure? Flat hash-keyed files or nested by stage?
- Metadata per artifact? (creation time, stage, inputs, outputs)
- Garbage collection? Content-addressed stores grow forever without it
- "Changing one rule re-runs only downstream stages" requires a dependency DAG over artifacts — this is a build system

**Recommendation for v1:** Timestamped run directories with stage-level checkpoints. `--resume` re-runs from the last completed stage. Content-addressed caching is a v2 optimization.

#### 6. Hindi golden set is critical path and unstarted

> *"Hindi accuracy on your scans is unmeasured. Build the Hindi golden set in M3."*

But M3 depends on it for validation. Creating human-verified ground truth for Hindi OCR across multiple exam types is expensive manual work (10+ person-days). This should start immediately and run in parallel with M1.

#### 7. IR schema is incomplete

Missing representations for:
- **Tables** (match-the-column in NEET) — only mentioned in S5, not in the schema
- **Passages** (shared stem across multiple questions in JEE/UPSC) — the Question schema has no `passage_ref` field
- **Answer keys** — section 14 asks "whether answer keys are in scope" but the schema has no answer field
- **Integer-type questions** (JEE Advanced) — `numeric` kind exists but no `answer_range` or `decimal_places`
- **Sub-questions** (JEE Advanced passages with parts a, b, c) — no parent-child relationship in the schema

#### 8. Watermark removal is the hardest unsolved problem

The ladder is well-described, but:
- "Near-opaque overlays destroy information" has no quantitative threshold for abandonment
- "SVG redraw" as a fallback requires an agent that understands circuit diagrams, biological diagrams, geometric constructions — this is an open research problem
- The "residual metric" is undefined (correlation with what? the estimated matte has its own errors)

**Recommendation:** Define watermark severity tiers (transparent text, semi-transparent logo, opaque overlay) with explicit strategies and give-up thresholds per tier.

#### 9. No concrete HTML output specification

"Bilingual 50/50 grid" with "continuous flow" and "break-inside avoid" is a CSS layout description, not a specification. CSS print behavior varies across browsers. `@page { margin: 0 }` doesn't suppress headers/footers in all browsers (Firefox ignores it; user must uncheck "Print headers and footers").

**Recommendation:** Build an HTML prototype in M1 and test it in Chrome, Firefox, and Edge print preview. Pin to Chromium if cross-browser print is intractable.

#### 10. G5 (Reproducible) conflicts with LLM usage

LLM outputs are not deterministic even at temperature 0 (quantization noise, batching, model version updates). If the agent is part of the pipeline, bit-identical outputs across runs are not guaranteed.

**Recommendation:** Cache all agent decisions keyed by `(input_hash, prompt_hash, model_version)`. On rerun, replay cached decisions. New runs with a different model version are treated as new runs. Document this caveat in G5.

---

### 5 Over-engineering risks

| Feature | Risk | Simpler alternative for v1 |
|---|---|---|
| YAML spec with versioned rules, hash tracking, diff-based patches | Weeks of tooling for what is a config file | Python dataclass with YAML serialization |
| Content-addressed artifact store with dependency DAG | Building a mini Bazel | Timestamped run dirs + `--resume-from-stage` |
| Dual-surface adapters (direct + MCP) per engine | 2× adapter maintenance | Direct Python calls only |
| `learn` CLI command with automatic regression test generation | Undefined learning loop | Manual ledger review → committed test cases |
| Interactive review page with patch writer | Full web app | JSON report + simple HTML viewer |

---

## Part 2 — Effort Estimation

### By milestone (1 developer, full-time)

| Milestone | Scope (v1 cuts applied) | Weeks | Key risk |
|---|---|---|---|
| **M1 Spine** | CLI, config, sequential runner, run dirs, resume, IR schema, basic S0+S9 | **2–3** | Getting the IR schema right |
| **M2 Cleaning** | PDF-layer removal, divide-normalize, basic furniture detection | **4–5** | Watermark estimation memory |
| **M3 Dual parse** | PaddleOCR adapter + Tesseract verifier, schema normalization, alignment | **4–5** | Hindi accuracy unknowns |
| **M4 Exam structure** | NEET template, question segmentation, numbering continuity, bilingual pairing | **3–4** | Cross-page stitching edge cases |
| **M7-lite Verify** | L1–L4 validators, basic fault injector | **2** | — |
| **M5 Math+Hindi** | LaTeX rendering, formula round-trip, Hindi NFC/lexicon | **4–5** | Formula verification reliability |
| **M6 Figures** | Figure detection, native extraction, box refinement, crop post-processing | **3–4** | Label vs. stray text classification |
| **M7-full Verify+Repair** | L5–L7, review page, overrides | **3–4** | Render round-trip accuracy |
| **M8 Efficiency** | Memory optimization, caching, telemetry, report | **2–3** | — |
| **Total** | | **27–35** | |

> **~7–9 months** for 1 developer. **~4–5 months** with 2 developers (M2/M3 and M5/M6 parallelize well).

### Parallel work (non-code)

| Task | Effort | Can start |
|---|---|---|
| Hindi golden set (10–15 pages, human-verified) | 10–15 person-days | Immediately |
| Synthetic watermark benchmark (apply known marks to clean pages) | 3–5 days | During M2 |
| NEET template authoring (3–5 years of papers analyzed) | 3–5 days | During M4 |
| HTML print layout prototype + cross-browser testing | 2–3 days | During M1 |

---

## Part 3 — Gaps Filled & Polishing

### New sections to add to the architecture doc

#### Non-goals

ExamForge does NOT:
- Generate answer keys or solutions
- Grade or score exams
- Support redistribution or commercial printing
- Handle handwritten answer sheets or OMR
- Perform translation (it preserves existing bilingual content)

#### Dependencies and prerequisites

| Dependency | Purpose | Install |
|---|---|---|
| Python 3.11+ | Runtime | System |
| PyMuPDF (fitz) 1.24+ | PDF handling, rendering, text/image extraction | `pip install pymupdf` |
| PaddleOCR | Primary OCR engine | `pip install paddleocr paddlepaddle` |
| Tesseract 5.x | Verification OCR | System install + `pip install pytesseract` |
| Playwright + Chromium | Formula rendering, HTML verification | `pip install playwright && playwright install chromium` |
| Pillow, NumPy, OpenCV | Image processing | `pip install pillow numpy opencv-python-headless` |
| Pydantic 2.x | IR schema validation | `pip install pydantic` |
| Click | CLI framework | `pip install click` |
| Jinja2 | HTML template rendering | `pip install jinja2` |

**Hardware:** 8 GB RAM minimum (16 GB recommended for watermark estimation). CPU-only. ~500 MB disk per exam paper in the run directory.

#### Configuration

```yaml
# examforge.yaml (user config, not the spec)
engines:
  paddleocr:
    lang: ["en", "hi"]
    use_gpu: false
  tesseract:
    lang: "eng+hin"
    binary: null  # auto-detect
browser:
  executable: null  # auto-detect via Playwright
  pool_size: 2
  timeout_ms: 30000
agent:
  enabled: false  # v1 default: no LLM
  provider: null
  model: null
  api_key_env: "EXAMFORGE_AGENT_API_KEY"
  budget:
    max_calls_per_page: 10
    max_cost_per_run_usd: 1.00
paths:
  runs: ./runs
  ledger: ./ledger
  cache: ./.cache
```

#### Disputed block resolution policy (when agent is disabled)

1. If one engine has confidence > 0.9 and the other < 0.5 → take the high-confidence reading
2. If both have confidence > 0.7 and text differs → take the primary engine (E1), mark as `disputed`
3. If both have confidence < 0.7 → mark as `disputed`, flag for human review
4. Cross-language invariant mismatch → take the reading that satisfies invariants, mark as `repaired`
5. All disputed items appear in the report with crops for human verification

#### IR schema additions

```python
# Additions to the existing schema
@dataclass
class Table:
    id: str
    page: int
    bbox_px: tuple[int, int, int, int]
    rows: list[list[Cell]]  # Cell has text, lang, colspan, rowspan
    sources: list[EngineSource]
    status: Status

@dataclass  
class Passage:
    id: str
    text_en: list[Block]
    text_hi: list[Block]
    question_refs: list[str]  # question IDs that reference this passage

@dataclass
class Question:
    # ... existing fields ...
    passage_ref: str | None  # link to parent Passage
    parent_question: str | None  # for sub-questions (JEE Advanced)
    sub_questions: list[str]  # child question IDs
    answer: Answer | None  # if answer key is in scope
    tables: list[Table]

@dataclass
class Answer:
    correct_options: list[str]  # ["A"] or ["A", "C"] for multi-correct
    numeric_value: float | None
    numeric_range: tuple[float, float] | None
```

#### Watermark severity tiers

| Tier | Description | Strategy | Give-up threshold |
|---|---|---|---|
| **W0 None** | No watermark detected | Skip S2 watermark step | — |
| **W1 Text-layer** | Watermark in PDF text layer only | Remove PDF objects, re-extract | If text diff shows content loss |
| **W2 Transparent** | Alpha < 0.3, distinct from content | Multi-page estimate + divide | Residual correlation > 0.15 |
| **W3 Semi-opaque** | Alpha 0.3–0.7, overlaps content | Estimate + divide + residual bridging | Residual correlation > 0.25 |
| **W4 Opaque** | Alpha > 0.7 or baked into image | Classical inpainting for small areas | If area > 20% of any figure → human |
| **W5 Baked** | Indistinguishable from content | Human or clean source copy | Always escalate |

---

## Part 4 — Revised Milestone Plan

### M1: Spine (Target: 2 weeks)

> **Exit:** `examforge execute --exam sample.pdf --mode fast` runs S0→S9 on a clean (no watermark) NEET paper, produces HTML output, and `--resume` restarts from the last completed stage.

| # | Task | Days | Notes |
|---|---|---|---|
| 1 | Package structure + `pyproject.toml` | 0.5 | Match section 12 layout |
| 2 | CLI with Click (`execute`, `resume`) | 1 | `--exam`, `--mode`, `--spec` flags |
| 3 | Config system (Pydantic Settings) | 1 | `examforge.yaml` + env vars + CLI overrides |
| 4 | Spec loader (dataclass, not full YAML system) | 1 | Rules as an enum, severity as a field |
| 5 | IR schema (Pydantic models) | 1.5 | Block, Question, ExamDocument, Table, Passage |
| 6 | Stage interface + sequential runner | 1.5 | `Stage.run(ctx) -> StageResult`, per-page status tracking |
| 7 | Run directory + manifest | 1 | Timestamped dirs, `manifest.json` with config hash |
| 8 | Resume logic | 1 | Detect last completed stage per page, restart |
| 9 | S0 intake (basic) | 1 | PyMuPDF open, page count, DPI, page images, text-layer check |
| 10 | S9 package (basic) | 1 | Dump IR to JSON + minimal Jinja2 HTML template |
| 11 | Unit tests | 1.5 | Schema validation, runner, resume, manifest |
| | **Total** | **~12** | |

### What M1 deliberately skips

- Content-addressed hashing (use timestamped dirs)
- DAG-based parallelism (sequential is fine for now)
- Spec patching and diff workflow (direct YAML editing)
- MCP adapters (direct Python calls only)
- Agent integration (no LLM calls in v1 spine)

### M2–M8: Unchanged from estimate above

Detailed task breakdowns for M2+ should be written when M1 is complete, informed by what we learn from the first end-to-end run.

---

## Part 5 — Questions for you before building

Before I start M1, I need decisions on:

1. **Target exam for v1:** NEET-UG? (recommended — highest volume, most standardized format)
2. **Do you have sample PDFs?** I need at least one clean paper and one watermarked paper to develop against.
3. **Answer keys in scope?** If yes, the IR schema needs an Answer model. If no, we skip that complexity.
4. **Python version:** 3.11+ or 3.12+? (3.12 has better error messages and performance)
5. **Package manager:** pip + venv, or uv? (uv is faster but newer)
6. **Are you willing to create the Hindi golden set?** This is manual work that only a Hindi-literate person can do. It blocks M3 accuracy validation.
