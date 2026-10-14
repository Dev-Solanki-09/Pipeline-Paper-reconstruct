# ExamForge v2.0 Architecture & Engineering Reference

ExamForge is an autonomous, token-efficient, deterministic exam paper reconstruction pipeline. It transforms raw, scanned, degraded, or digital Indian exam papers into clean, printable, accessible, bilingual HTML and structured data artifacts.

---

## 1. System Topology & Directed Acyclic Graph (DAG)

The reconstruction pipeline operates as a topologically sorted Directed Acyclic Graph (DAG) with 10 canonical stages following the **digital-first, model-last** paradigm:

```
[ Input Exam PDF / Scans / Archives ]
                 │
                 ▼
          ┌─────────────┐
          │  S0 Intake  │ ── Inspection, decompression, 50MP bomb guard, path classifier (A/B/C)
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │ S1 Profile  │ ── Consensus fingerprinting, autoprofiling cache (cheap PDF text probe)
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │  S2 Clean   │ ── Conditional deskew, illumination, watermarks & coordinate lock
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │  S3 Parse   │ ── Path A zero-model font decode; Path B warm dual-engine OCR (PP-OCR, Paddle-VL)
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │S4 Structure │ ── Multi-column, reading order, question grouping & 0-token bank reuse
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │S5 Normalize │ ── Single-pass math, chemistry & Devanagari normalization with edit budget
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │ S6 Figures  │ ── Spatial grid primitive clustering, vertical baseline ordering, tables
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │  S8 Verify  │ ── Tier-gated rules (FREE/IO/HEAVY), consolidated validators (10 rules)
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │  S7 Repair  │ ── NetBenefitLedger, LLM eligibility gating, token budget, T0–T4 escalation
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │ S9 Package  │ ── Template v2 rendering, lazy-loaded exporters (HTML/MD/JSON/QTI)
          └─────────────┘
```

---

## 2. Core Subsystems

### Intermediate Representation (IR v2)
- **Discriminated Union Content Nodes**: `TextNode`, `MathNode`, `TableNode`, `FigureNode`, `StatementsNode`, `MatchColumnsNode`, `CodeNode`, `BlankNode`, `RawCropNode`.
- **Question Hierarchy**: Root questions, subparts `(a)(b)(c)`, internal choice groups (`OR`/`अथवा`), comprehension passage linking.
- **Answer & Marking Schemes**: Canonical `AnswerSpec` (single, multi, numeric range, bonus), marking formulas (+4/-1, partial credit).

### Multi-Path Page Execution (Digital-First, Model-Last)
- **Path A (Digital Vector PDF)**: Pages with valid font encodings completely bypass vision/OCR model inference. Lines, baselines, and sub/superscripts are extracted directly from PDF fonts at near-zero CPU and memory cost.
- **Path B (Degraded Scan)**: Dual-engine OCR (PP-OCR + Paddle-VL) using process-level warm model caching and spatial grid clustering.
- **Path C (Embedded / Legacy Glyphs)**: GlyphDecoder with font glyph caching.

### Declarative Exam Profiles & Compute Tiers
- **Profile Inheritance**: Profiles extend base configurations (`extends: [generic_bilingual]`).
- **Consolidated Compute Tiers**: `lite` (low RAM ≤ 2.5 GB), `standard` (6 GB), and `gpu` with memory ceilings and capability negotiation unified across config and execution profiles.

### Consolidated Deterministic Verifiers (10 Rules across Cost Tiers)
- **Cost Tier FREE (In-Memory AST)**:
  - `R01_R02_furniture_branding`: Repeating headers/footers, URLs, phone numbers, and page number scrubbing with subpart protection.
  - `R05_R10_language_consistency`: Numerical invariant preservation, script layout, and bilingual text alignment.
  - `R06_R14_R15_structure_integrity`: Option completeness, subpart nesting, QuestionKind shapes, and monotonic sequence continuity.
  - `R07_chemical_equations`: Balanced chemical equations and stoichiometry.
  - `R08_spatial_containment`: Bounding box validity, page margin containment.
  - `R09_cross_references`: Inter-question and passage reference integrity.
- **Cost Tier IO (Filesystem / Render Validation)**:
  - `R03_watermarks`: Residual watermark correlation.
  - `R04_R13_packaged_output_check`: KaTeX math syntax, offline CSP compliance, standalone HTML validity.
  - `R16_answer_binding`: Answer key referential integrity and duplicate detection.
- **Cost Tier HEAVY (Dual-Engine / Model Verification)**:
  - `R11_R12_text_agreement_lexicon`: OCR vs text-layer agreement and STEM lexicon compliance.

### Escalation Ladder & Repair Safety (S7)
- **NetBenefitLedger**: Records validator status before and after every repair attempt; auto-disables harmful repair tiers if harm rate exceeds 0.1%.
- **LLM-Eligibility Gating**: Only BLOCKER severity issues with localized bounding boxes and candidate text escalate to LLM repair; non-critical WARN issues never trigger model repair.
- **Per-Paper Caps & Token Budget**: Strict per-paper token and repair attempt ceilings halting repairs with code 20 (`review.html`) upon exhaustion.
- **T0–T4 Escalation Ladder**:
  - `T0 Deterministic Fix`: Targeted gap search recovery and lexicon lookup (0 tokens).
  - `T1 Local Re-Parse`: Local crop OCR second opinion (0 tokens).
  - `T2 Cheap VLM Index Choice`: Small model candidate choice from contact sheet (~1 token output).
  - `T3 Strong Model JSON Patch`: Constrained RFC 6902 patch with digit/unit preservation invariant.
  - `T4 Human Review`: Safe fallback emitting `review.html` and exit code 20.

### Verified Question Bank & Lessons Store
- **SimHash-64 & Number Signatures**: Strict number signatures and NFC normalization prevent false reuses.
- **Self-Improving Loop**: Autonomous lesson recording on validated repairs, BM25 retrieval, and recurrence promotion.

### Multi-Format Exporters
- `HTMLExporter`: Standalone single-file HTML with embedded base64 figures and offline CSP.
- `JSONExporter`: Full IR v2 serialization.
- `MarkdownExporter`: KaTeX math and clean markdown layout.
- `JSONLExporter`: Streaming question dataset.
- `QTIExporter`: IMS QTI-lite standard with unsupported feature sidecar report.
