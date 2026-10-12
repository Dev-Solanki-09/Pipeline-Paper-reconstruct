# ExamForge: Architecture and Build Plan for a Maximum-Accuracy Exam Reconstruction Pipeline

*Working name: ExamForge. Architecture, algorithms, verification and build order. October 11, 2026.*

## 1. Goal and guarantees

Turn scanned or digital Indian exam papers (NEET-UG, JEE, UPSC and similar) into one continuous, printable, bilingual (English and Hindi) HTML file with correct text, accurate formulas and clean diagrams, and with no header, footer, branding, page number or watermark anywhere, including inside images.

Five guarantees drive the design:

- **G1 Fail closed.** A run succeeds only when every blocker rule in the frozen spec passes.
- **G2 No silent loss.** Content is dropped only with positive evidence that it is furniture, and every drop is logged with a reason.
- **G3 No invented content.** A text change needs independent evidence, never the agent's opinion alone.
- **G4 Measured accuracy.** Each run reports an audited defect-rate estimate instead of a claim.
- **G5 Reproducible.** Same input, spec and engine versions give identical output.

Literally zero errors on every scan cannot be promised. What is promised is that leftover uncertainty is isolated, shown with evidence and routed to review rather than shipped. The design target is a modest CPU-only machine with limited RAM; GPU or cloud engines are optional accelerators.

## 2. Design principles

1. **Deterministic spine, AI at the edges.** A state machine decides what runs and when. The agent answers bounded questions and can never skip a stage.
2. **Every requirement is a rule.** Prompts express intent; code checks enforce it.
3. **Redundancy is the accuracy engine.** Two OCR engines, two languages, a render round-trip and an independent third reader cross-check each other.
4. **Cheap checks first.** Expensive engines and agent vision run only on flagged items (except in max mode).
5. **Localize everything.** Every element carries page, box, engine and transform provenance, so fixes stay surgical.
6. **Cache and version everything.** Artifacts are content-addressed and runs live in versioned directories.
7. **Learn only through reviewed changes.** Failures are recorded automatically; thresholds and templates change only via reviewed commits backed by tests.

## 3. Architecture

```
input -> S0 intake -> S1 normalize -> S2 clean -> S3 dual parse -> S4 exam structure
      -> S5 math and Hindi -> S6 figures -> S7 render -> S8 verify and repair -> S9 package
                                                 ^---- bounded repair loop ----|
```

- **Orchestrator.** A DAG over pages x stages with per-page parallelism, a resource governor (RAM and CPU), token, time and cost budgets, atomic writes and resume after a crash.
- **Stage contract.** Each stage takes typed inputs and returns outputs, metrics and an issue list. Pre-conditions and post-conditions are validated, and a violated post-condition stops the run.
- **Artifact store.** Files are keyed by a SHA-256 of content plus parameters plus engine version, so changing one rule re-runs only the downstream stages.
- **Dual-surface adapters.** Bulk work calls engines directly (Python library or HTTP) to avoid process hops. The same engines are also exposed as MCP servers so the agent can take an interactive second look at a disputed region. MCP is valuable when an agent chooses tools; deterministic bulk work does not need it.

## 4. Spec-driven commands

Your requirements live in one frozen spec file. Every rule names a check and a severity. The spec hash is written into the HTML metadata and the run manifest, so any output can be traced to the rules it satisfied.

```
spec_version: 1
rules:
  R01_no_furniture: {severity: blocker, check: no_headers_footers_page_numbers}
  R02_no_branding:  {severity: blocker, check: no_brand_text_or_logo, learn_from_input: true}
  R03_no_watermark: {severity: blocker, check: watermark_residual, max_corr: 0.05}
  R04_continuous:   {severity: blocker, check: no_page_wrappers_or_breaks}
  R05_bilingual:    {severity: blocker, check: en_hi_pairs_complete}
  R06_complete:     {severity: blocker, check: numbering_continuity}
  R07_formulas:     {severity: blocker, check: formula_roundtrip}
  R08_figures:      {severity: blocker, check: figure_clean_border_and_present}
  R09_unicode:      {severity: warn,    check: devanagari_nfc_and_lexicon}
modes:
  fast: {engines: [E1], second_engine: on_flag, audit_sample: 0.05}
  max:  {engines: [E1, E2], second_engine: always, audit_sample: 0.10}
```

Thresholds shown are initial values to calibrate on the benchmark. A free-text command is compiled into a spec patch, shown back to you as a diff, and frozen only after you approve it. The one command is execute, with flags for exam and mode.

## 5. Intermediate representation

All engines and stages speak one schema, validated at every hand-off.

```
Block:    id, page, type, bbox_px, bbox_norm, order, lang, text, latex, conf,
          sources[{engine, text, conf}], crop_ref,
          status (trusted | disputed | repaired | human | dropped), drop_reason
Question: no, section, kind (mcq1 | mcqn | numeric | match | assertion | passage),
          stem{en[], hi[]}, options[{label, en[], hi[], figure}], figures[], tables[], marks
```

## 6. Stage design

### S0 Intake and triage

- Classify the source: digital text layer, scan, phone photo or mixed.
- **Legacy-font trap.** Many Indian PDFs use pre-Unicode Hindi fonts (Kruti Dev, Chanakya, DevLys), so extracted text looks like Latin gibberish. Detect it from font names and a Devanagari-validity score; if the text layer is bad, ignore it and OCR the page.
- Per-page metrics: DPI, skew, orientation, blur (Laplacian variance), noise, contrast, column count, two-page spreads (split them) and page class (cover, instructions, questions, answer key, rough work, blank, OMR).
- **Harvest furniture before deleting it.** Exam name, series code and date go into the manifest (never the HTML) and select the exam template.
- Detect annotation ink (pen marks, highlights, stamps) by colour and stroke statistics when the print is black.
- Profile the watermark: per-pixel percentile across pages, ghost energy, and a class (none, text layer, image layer, tiled, single logo, baked in). The output is a profile that picks the strategy per page.

### S1 Normalize

- Fix orientation, deskew, and correct perspective or dewarp photos. Flatten illumination on OCR copies only.
- Keep original pixels and store every transform so boxes map back to the source. Align pages (ECC) for the watermark estimator.
- Upscale only OCR inputs when DPI is low. Never use super-resolution for final crops, because it can invent strokes.

### S2 Clean (watermark, furniture, annotation ink)

A ladder, with the winner chosen per page by metrics:

1. **Source-level removal** for digital PDFs: objects present on at least 80% of pages, text rotated about 45 degrees or with alpha below 1, and optional-content layers named like watermarks. Re-extract text afterwards and diff it to confirm no content was lost.
2. **Multi-page estimate:** strip-wise percentile (bounded memory), per-page gain and offset regression to absorb scanner variation, then divide.
3. **Single-image method:** closing then divide, with the kernel between line width and logo stroke width; use the channel where a coloured logo is faintest.
4. **Residual bridging:** mask only pixels where information is destroyed. For line art, skeletonize, pair collinear endpoints across the gap and draw the continuation. Use classical inpainting for tiny gaps. Generative inpainting is a last resort and always flagged.
5. **Selection metrics:** correlation with the estimated matte, stroke-width continuity across the mask seam, OCR confidence change, and absence of ringing.

Branding in the body is handled by rules plus learning: anything repeated at the same normalized position across pages is a furniture candidate, QR codes, URLs and phone numbers are matched by pattern, and logos are found by template matching with the estimated matte.

### S3 Dual parse

- **E1** PaddleOCR-VL (official API or self-hosted), **E2** Docling (local CPU) or MinerU, **E3** Tesseract (Hindi and English) as a cheap independent reader for round-trip checks. The agent's vision is the tiebreaker, not a bulk engine.
- Adapters normalize everything to the schema, with retries, backoff, timeouts and a circuit breaker. If an engine is down, fall back and mark those pages single-engine so the gates tighten.
- Align engine outputs by box overlap and text similarity, then align tokens at grapheme-cluster level for Devanagari. The result is a list of dispute items, each with the exact span and a crop.
- **fast** runs E1 on every page and E2 only on flagged pages. **max** runs both everywhere.

### S4 Exam structure

- Per-exam templates define question-number patterns, option styles ((1) to (4), (A) to (D), Hindi labels), sections, marking text and the expected question count. For an unknown exam the agent drafts a template, which is schema-checked and human-approved once, then reused.
- Segment questions and stitch those that cross pages or columns.
- **Numbering continuity** is solved as a sequence alignment of detected numbers against 1 to N. Gaps give the exact regions to re-parse.
- **Bilingual pairing** by number, then by semantic similarity. Side-by-side, interleaved and separate-booklet layouts are all supported.
- **Cross-language invariants.** Digits, units and formula tokens must match between the English and Hindi halves. A mismatch points to an OCR error in one half and often fixes it.
- **Reference rule.** A stem that mentions a figure, diagram, graph, circuit or table must have one; otherwise raise a missing-figure issue.
- Typed question kinds cover assertion-reason, match-the-column, statement sets, passages and numeric answers.

### S5 Math, chemistry, Hindi

- **Formulas.** Canonicalize both engines' LaTeX by parsing to an AST and compare. Pre-render all formulas in one browser session to inline SVG, then round-trip: compare glyph counts, aspect ratio and structure against the source crop, and re-recognize the render to compare ASTs.
- **Chemistry.** Subscripts, charges and arrows are text; skeletal structures are figures. An optional module converts structures to SMILES and back to clean SVG, accepted only after a round-trip comparison.
- **Hindi.** Handle legacy fonts, NFC normalization, nukta and zero-width-joiner policy, danda versus pipe, and matra versus 1, l or pipe confusions. Preserve the source's digit script. Flag out-of-vocabulary tokens with a Hindi lexicon plus a science glossary, then adjudicate on crops. Build a Hindi golden set early, because public benchmarks are mostly English and Chinese.
- **Tables.** Compare cell grids between engines (TEDS-style) and treat match-the-column as a structured table.

### S6 Figures

- Candidates come from engine figure boxes plus our own detection of large non-text ink components, then are classified as diagram, formula, table, logo or QR.
- **Prefer native assets.** Digital PDFs give embedded images at source quality, and vector drawings can be extracted as true SVG.
- **Box refinement.** Grow the box until the ring around it is clean (clean-border test) within caps. Absorb labels inside or touching the figure (short tokens like A, 30 degrees, 5 ohm). Paint out stray stem or option text that overlaps the box, using layout masks.
- Crop from the cleaned high-DPI render. Output lossless palette or grayscale PNG for line art, or SVG for vectors. Preserve physical size in CSS millimetres so print scale matches the paper.
- Post-process: background to pure white by divide-normalization, denoise without eroding thin lines, no sharpening halos.
- Assign each figure to its question or option slot, detect duplicates by perceptual hash, and run a watermark-residual check per figure.
- Optional: the agent redraws simple diagrams as SVG, accepted only if an overlay diff passes.

### S7 Render

- Deterministic Jinja2 templates fed from the schema. The agent never writes free-form HTML.
- Math is pre-rendered to inline SVG. Devanagari and Latin fonts are subset and embedded, with lang attributes and line-height tuned for matras. Output is a single file (base64 assets) or an assets folder.
- Continuous flow with a bilingual 50/50 grid. Use break-inside avoid on questions and figures. Set @page margin to 0 with body padding so Chromium-based browsers do not add their own headers and footers (verify in other browsers). No page wrappers or page-break markers.
- Stable IDs and sorted attributes so output diffs cleanly. Provenance attributes appear in a debug build only.

### S8 Verify and repair

See sections 7 and 8.

### S9 Package

Final HTML and assets, a report page, the manifest, the dropped-content log, the ledger delta and an exit code.

## 7. Verification stack

| Layer | Check | Catches |
| --- | --- | --- |
| L1 | Stage post-conditions: schema and counts | Structural breaks |
| L2 | Engine agreement | OCR errors |
| L3 | English vs Hindi invariants | Errors both engines share |
| L4 | Numbering, option counts, figure references | Drops, merges, missing figures |
| L5 | Render round-trip: screenshot per question, third-engine OCR, compare to schema | Rendering and encoding bugs |
| L6 | Visual QA agent: original and render side by side, structured verdict | Subtle layout defects |
| L7 | Lint: brand lexicon, watermark residue, furniture, QR and URL, HTML validity, size budgets | Spec violations |
| L8 | Human review page | Everything unresolved |

- **Gate sensitivity tests.** A fault injector corrupts a known-good output (delete an option, swap digits, clip a figure, reintroduce a watermark) and every injected fault must be caught. Validators are tested to fail, not just to pass.
- **Audited accuracy.** L6 runs on all flagged questions plus a random sample. Each run reports an estimated defect rate with a confidence interval, and the release gate uses the upper bound.
- **Overrides.** Human edits are stored as keyed patches (element ID, content hash, evidence) that re-apply on reruns, so manual fixes survive.

## 8. Agent protocol

- **Roles.** Adjudicator (choose or compose a reading from crops and candidates), Repairer (choose from a fixed operation menu), Planner (draft exam templates), Reviewer (structured verdicts).
- **Repair menu.** Adjust box, re-crop, re-run an engine with a parameter, merge or split blocks, reclassify a block, set text with evidence. No shell, no arbitrary code, no network beyond the engines.
- **Constraints.** Temperature 0, JSON-schema outputs, per-issue and per-run budgets, bounded retries, tight crops, verdicts cached by crop hash, every call logged for replay. Page text is data, never instructions.
- **Evidence rule.** An edit is {old, new, evidence crop} and is accepted only if an independent engine agrees or two independent agent reads agree; otherwise it goes to a human.
- **Escalation ladder.** Heuristic fix, parameter retry, second engine, agent adjudication, second agent read, human review.
- **Learning.** Each failure becomes a ledger entry (signature, root cause, fix, minimized crop) and an automatic regression test. Threshold and template changes go through reviewed commits.

## 9. Efficiency engineering

- **Caching.** Content-hash cache; changing one rule re-runs only downstream stages.
- **Memory.** A 400 DPI A4 page is about 15 megapixels, and a 15-page float32 stack exceeds 2 GB. Estimate the watermark in 256-row strips from about 20 to 30 representative pages.
- **CPU.** Page-level process pool bounded by RAM, async engine calls with a concurrency cap, one reused browser for math and render checks, no per-item process spawns.
- **Progressive checking.** Regex and geometry first; second engine and agent only on flagged items in fast mode.
- **Agent cost.** Tight crops instead of full pages, cached verdicts, enforced budgets.
- **Output size.** Palette PNG or SVG for line art, optional lossless WebP, an oxipng pass, font subsetting, and math SVG deduplicated by formula hash.
- **Telemetry.** Per-stage time, cache hit rate, cost and issues per 100 questions go into the report so tuning is data-driven.

## 10. Failure-mode catalogue

| Failure | Detection | Automatic response | Escalation |
| --- | --- | --- | --- |
| Legacy-font Hindi gibberish | Font names, validity score | Ignore text layer, OCR | None |
| Engine timeout or quota | Timeout, HTTP status | Retry, backoff, fallback, mark single-engine | Review if gates fail |
| Rotated, mixed or two-page scans | Orientation, aspect ratio, gutter | Rotate or split | Review if low confidence |
| Low DPI or blur | Metrics | OCR-only upscale, tighter gates | Review |
| Pen marks, highlights | Colour and stroke stats | Remove by channel | Review if overlapping text |
| Watermark over diagram | Residual metric | S2 ladder | SVG redraw or human |
| Question split across page or column | Numbering alignment | Stitch | Review |
| Missing or merged question numbers | Continuity check | Targeted re-parse | Review |
| Clipped arrowheads or subscripts | Border-ink test | Grow box | Review |
| Stray stem text inside figure crop | Layout-mask overlap | Paint out or trim | Review |
| Hindi matra or conjunct errors | Lexicon, EN-HI invariants | Adjudicate on crop | Human |
| Formula misread | AST disagreement, round trip | Second engine, agent | Human |
| Unknown exam layout | Template mismatch | Agent drafts template | Human approves once |

Security: parse untrusted PDFs in a subprocess with CPU, memory and time limits, pin dependencies by hash, and give the agent no network or shell.

## 11. Testing and benchmarks

- **Golden corpus** of 15 to 20 papers across exams, years, scan qualities and watermark types, with human-verified ground truth.
- **Metrics:** question completeness, grapheme error rate (English and Hindi), formula AST match, figure box IoU and clipping rate, watermark residual, defects per 100 questions, time per page, cost per paper.
- **Synthetic suites.** Apply known watermarks (alpha, colour, rotation, tiling) and degradations (blur, noise, JPEG, skew) to clean pages. This gives ground truth for the cleaning module and for threshold calibration.
- Gate sensitivity tests (section 7), regression tests generated from the ledger, and golden-file HTML diffs.
- **Upgrade rule.** Any engine or model version bump must pass the full corpus before merging.
- Accuracy targets are hypotheses: set them after the first benchmark, then ratchet them up.

## 12. Repository layout, CLI and exit codes

```
examforge/
  spec/        default.spec.yaml, exams/{neet,jee,upsc}.yaml
  src/examforge/
    cli.py                     execute | resume | review | audit | bench | learn
    orchestrator/              dag, store, manifest, budget
    stages/                    s0_intake ... s9_package
    adapters/                  paddle, docling, mineru, tesseract, agent, browser_pool
    ir/                        schema, normalize, align
    validators/                registry + one module per rule
    agent/                     roles.yaml, prompts/, schemas/
    review/                    static review page + patch writer
  tests/                       unit, synthetic, regression, golden
  ledger/                      failures.jsonl
  runs/                        versioned run directories (git-ignored)
```

Exit codes: 0 all gates pass, 10 pass with warnings, 20 needs human review, 30 failed. Automation chains on these.

**Migration from the current prototype.** Split universal\_pipeline.py into stages S0 to S9 behind the same execute command, turn prompt.md into per-role agent prompts, and keep the versioned run directories and the failure ledger as the learning source. RUNBOOK.md reduces to: run execute, read the exit code, open the review page on 20, never hand-edit output.

## 13. Milestones and exit criteria

1. **M1 Spine.** CLI, spec, orchestrator, store and manifest, with one clean paper end to end. Exit: reruns are identical and resume works.
2. **M2 Cleaning.** The S2 ladder plus the synthetic benchmark. Exit: residual metric under threshold on the synthetic suite.
3. **M3 Dual parse.** Adapters, schema, alignment and the Hindi golden set. Exit: engine-disagreement report on the golden papers.
4. **M4 Exam structure.** Templates, continuity, bilingual pairing and invariants. Exit: all pass on the golden papers.
5. **M5 Math and Hindi.** Formula round-trip and lexicon flags. Exit: formula and Hindi error rates measured.
6. **M6 Figures.** Clean-border growth, label absorption, native assets. Exit: clipping and residue rates under target.
7. **M7 Verify and repair.** Full stack, review page, overrides. Exit: every injected fault caught.
8. **M8 Efficiency and audit.** Strip processing, tuned caching, audit sampling, report. Exit: time, cost and defect-rate estimate recorded per paper.
9. **M9 Optional.** Chemistry structures to SVG, SVG redraw of simple diagrams, more exams.

The order matters: cleaning comes before parsing because watermark text pollutes OCR, and verification infrastructure comes early so every later module is measured from the start.

## 14. Risks and open questions

- **MCP maturity.** Some servers are young or marked unstable. The adapter layer isolates you from that, and bulk work should prefer direct library or API calls.
- **Hindi accuracy on your scans is unmeasured.** Build the Hindi golden set in M3.
- **API limits and cost.** Free tiers throttle, so batch, cache or self-host.
- **Watermark strength.** Near-opaque overlays destroy information, so the ladder ends in SVG redraw or a clean source copy.
- **Source terms.** Printing for personal use differs from redistribution.
- **Version drift.** Pin engines and run the corpus before upgrading.
- **Open questions:** the mix of digital and scanned sources, the watermark types seen so far, which exam to support first, target hardware, and whether answer keys and solutions are in scope.
