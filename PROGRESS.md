# ExamForge v2 — Progress Ledger

> **Status:** Complete — v2.0.0 Released (All Gates 0–17 PASSED)  
> **Current Baseline:** 517+ passing tests | 0 regressions  

---

## Phase Checklist

- [x] **Phase 0: Reconnaissance, Baseline, and Test Harness**
  - [x] P0.T1: Repository mapping and reconciliation (`docs/RECON.md`)
  - [x] P0.T2: Set up `PROGRESS.md`, `BLOCKERS.md`, `DEPENDENCIES.md`
  - [x] P0.T3: Establish socket-blocking test fixture (`tests/conftest.py`)
  - [x] P0.T4: Gate 0 Verification (158 passing tests, zero network access)
- [x] **Phase 1: Telemetry Ledger & Isolated LLM Seam (`examforge/llm/`)**
  - [x] P1.T1: `src/examforge/telemetry.py` — Stage time, peak RSS memory, token counters, and ledger export
  - [x] P1.T2: `src/examforge/llm/types.py` — Structured requests, responses, token usage, and cost tracking
  - [x] P1.T3: `src/examforge/llm/budget.py` — Per-run, per-question, per-stage token budget governor
  - [x] P1.T4: `src/examforge/llm/cache.py` — Content-addressed (SHA-256) deterministic prompt/response cache
  - [x] P1.T5: `src/examforge/llm/fake.py` — Deterministic offline mock client for unit and integration testing
  - [x] P1.T6: `src/examforge/llm/recording.py` — Cassette recording and replay engine for deterministic tests
  - [x] P1.T7: `src/examforge/llm/client.py` — Unified LLM client facade routing through budget, cache, and recorder
  - [x] P1.T8: `tests/test_llm_boundary.py` — AST scanner test enforcing Rule 8 (provider isolation)
  - [x] P1.T9: Gate 1 Verification (all 178 unit tests, AST enforcement, offline determinism pass)
- [x] **Phase 2: IR Schema v2 & Strict Invariants System**
  - [x] P2.T1: `schema_version: int = 2` & `ContentNode` discriminated union (`TextNode`, `MathNode`, `TableNode`, `FigureNode`, `StatementsNode`, `MatchColumnsNode`, `CodeNode`, `BlankNode`, `RawCropNode`) with `LangCode`
  - [x] P2.T2: `Question` v2 (`stem`, `options`, extended `QuestionKind`, `children`, `choice_group`, `Marks`, `AnswerSpec`, `Provenance`), `Passage`, `DocumentPart`, and `LanguageInfo`
  - [x] P2.T3: Compatibility layer (computed properties `stem_text_en`, `stem_text_hi`, `text_str_en`, `text_str_hi`) and `migrate_v1_to_v2` / `load_document`
  - [x] P2.T4: `invariants.py` (unique IDs, referent resolution, monotone numbers, option labels, `choice_group` marks)
  - [x] P2.T5: Schema export (`schemas/examdocument.v2.json` and staleness test)
  - [x] P2.T6: Unit & property-based tests (`tests/test_ir_v2.py`, `tests/test_invariants.py`, `tests/test_migrator.py`)
  - [x] P2.T7: Gate 2 Verification (characterization byte-identical, schema exported, all tests green)
- [x] **Phase 3: Declarative Exam Profiles Architecture & Compute Tiers**
  - [x] P3.T1: `src/examforge/registry.py` — Generic typed `Registry[T]` with duplicate prevention and capability search
  - [x] P3.T2: `src/examforge/profiles/schema.py` — Declarative `ExamProfile` schema with validated sections
  - [x] P3.T3: `src/examforge/profiles/loader.py` — Profile inheritance (`extends`), deep-merge, cycle detection, and line-tracking loader
  - [x] P3.T4: Built-in profiles (`neet_ug`, `jee_main`, `jee_advanced`, `upsc_prelims`, `gate`, `cbse_board`, `sat_like`, `generic_mono`, `generic_bilingual`, `base`)
  - [x] P3.T5: Refactor all pipeline stages to consume `ctx.resolved_profile` and declare capabilities
  - [x] P3.T6: `PipelineRunner.negotiate_capabilities()` with fail/downgrade/warn policies
  - [x] P3.T7: `src/examforge/profiles/compute.py` & tier configs (`lite`, `standard`, `gpu`)
  - [x] P3.T8: `src/examforge/spec.py` — Deterministic `compute_spec_hash()` with checkpoint invalidation
  - [x] P3.T9: CLI subcommands (`examforge profile list|show|validate|diff`) and runner flags (`--profile`, `--compute`)
  - [x] P3.T10: `tests/test_no_hardcoding.py` AST scanner & allowlist guarding against hardcoded exam literals
  - [x] P3.T11: Gate 3 Verification (224/224 tests green, 10 profiles valid, characterization 25/25 Qs identical)
- [x] **Phase 4: Synthetic Ground Truth Generator (L0–L4), Gold Set & Evaluator**
  - [x] P4.T1: `data/corpora/` — License-free bilingual seed corpora for STEM domains
  - [x] P4.T2: `src/examforge/synth/generator.py` — Seeded, deterministic `SyntheticDocumentGenerator` emitting rich IR v2 `ExamDocument`s
  - [x] P4.T3: `src/examforge/synth/figures.py` — Programmatic STEM diagram generation (circuits, ray diagrams, coordinate graphs, mechanics pulleys)
  - [x] P4.T4: `src/examforge/synth/degrade.py` — Composable, seeded degradation ladder (L0 digital, L1 raster scan, L2 noise/blur/skew, L3 shadow/folds, L4 phone capture)
  - [x] P4.T5: `src/examforge/synth/matrix.py` — Greedy pairwise covering array generator producing 21 valid universal benchmark families (`tests/universal/families/*.yaml`)
  - [x] P4.T6: `src/examforge/eval/metrics.py` — Deterministic accuracy metrics: CER, WER, Sequence Accuracy, Count Match, Option Accuracy, IoU, Table Similarity
  - [x] P4.T7: `src/examforge/eval/scorer.py` — Full `ExamScorer` engine computing composite aggregate score and structured reports
  - [x] P4.T8: `src/examforge/eval/compare.py` & CLI commands — `examforge eval` (with `--compare` and `--write`) and `examforge compare`
  - [x] P4.T9: Unit & property test suite (`test_synth_generator.py`, `test_synth_figures.py`, `test_synth_degrade.py`, `test_synth_matrix.py`, `test_eval_metrics.py`, `test_eval_scorer.py`)
  - [x] P4.T10: Baseline capture (`metrics/baseline.json`), threshold calibration (`metrics/thresholds.yaml`), and documentation (`docs/BASELINE.md`)
  - [x] P4.T11: Gate 4 Verification (248/248 tests green, 0 regressions, all 21 universal families validated, E2E characterization 25/25 Qs verified)
- [x] **Phase 5: Free Verifiers & Extended Validators (R01–R15)**
  - [x] P5.T1: `src/examforge/validators/base.py` — `Validator` protocol and `FunctionValidator` adapter
  - [x] P5.T2: `src/examforge/validators/r10_language_consistency.py` — Bilingual invariant token cross-verification
  - [x] P5.T3: `src/examforge/validators/r11_text_layer_agreement.py` — Text layer ground-truth token overlap
  - [x] P5.T4: `src/examforge/validators/r12_lexicon.py` & `data/lexicons/` — STEM domain lexicons and OCR typo detection
  - [x] P5.T5: `src/examforge/validators/r13_render_check.py` — KaTeX/LaTeX syntax errors, broken images, and container artifacts
  - [x] P5.T6: `src/examforge/validators/r14_sequence_gaps.py` — Monotone numbering sequence gap and duplicate detector
  - [x] P5.T7: `src/examforge/validators/r15_structure_consistency.py` — Sub-part sequence, choice groups, and kind shapes
  - [x] P5.T8: `src/examforge/stages/s8_verify.py` — Issues streaming to issues.jsonl and rule breakdown metrics
  - [x] P5.T9: `tests/faults/test_fault_injection.py` — Fault-injection test suite with 100% precision/recall across 70 mutators
  - [x] P5.T10: Gate 5 Verification (267/267 tests green, 0 false positives on 200 clean seeds, characterization 25/25 Qs verified)
- [x] **Phase 6: Universal Multi-Column & Reading Order Engine**
  - [x] P6.T1: `src/examforge/layout/columns.py` — Whitespace projection, sustained gutter detection, and span classification (banners, passages, wide tables)
  - [x] P6.T2: `src/examforge/layout/reading_order.py` — Multi-strategy ordering (`columns_ltr`, `columns_rtl`, `xy_cut`, `parallel`) with metamorphic shuffling/scaling invariance
  - [x] P6.T3: `src/examforge/layout/languages.py` — Layout alignment (`parallel_columns`, `interleaved`, `separate_sections`, `monolingual`) with count mismatch alerts
  - [x] P6.T4: `src/examforge/layout/numbering.py` — Profile-driven regexes, label schemes, chemical formula guard (`2. SO3`), and monotonicity sequence enforcement
  - [x] P6.T5: `src/examforge/layout/nesting.py` — Sub-parts `(a)(b)(c)` and internal choice (`OR`/`अथवा`) `choice_group` detection
  - [x] P6.T6: `src/examforge/layout/passages.py` — Range-based comprehension passage detection and question linking
  - [x] P6.T7: `src/examforge/layout/kinds.py` — Deterministic question-kind classification heuristic (>=98% accuracy across 200 synthetic tests)
  - [x] P6.T8: `src/examforge/layout/parts.py` & `orientation.py` — Document parts (cover, instructions, questions, answer key, rough work) and two-up spread splitting
  - [x] P6.T9: `src/examforge/layout/redos.py` — Safe regex compilation and timeout/chunking ReDoS guard (<50ms on 100KB adversarial inputs)
  - [x] P6.T10: Stage S4 integration (`src/examforge/stages/s4_structure.py`) with `layout_v2` feature flag and clean v1 rollback
  - [x] P6.T11: Gate 6 Verification (317/317 tests green, 0 regressions vs baseline, ReDoS guard verified, rollback verified)
- [x] **Phase 7: Vector-First & Ink-Aware Figure Pipeline**
  - [x] P7.T1: `src/examforge/figures/vector.py` — PyMuPDF `get_drawings()` union-find clustering, repeated cross-page watermark vector hashing, separator rule filtering, and SVG/high-DPI PNG rendering
  - [x] P7.T2: `src/examforge/figures/raster.py` — Connected-component run-length clustering for scans
  - [x] P7.T3: `src/examforge/figures/crop.py` — `refine_bbox` grow-until-clean (border-strip ink ratio == 0), shrink-to-ink with padding, text mask subtraction while attaching in-figure labels, idempotent, monotone
  - [x] P7.T4: `src/examforge/figures/associate.py` — Multi-signal scoring, reading order, figure cues, option-grid containment, constrained greedy assignment, and unassigned figure issue emission
  - [x] P7.T5: `src/examforge/figures/resolution.py` — Clamped native DPI resolution policy and scale classes (`img-inline` … `img-lg`)
  - [x] P7.T6: `src/examforge/tables/` (`grid.py`, `vector.py`, `pipeline.py`) — Vector rulings to grid, header detection, structure validation, safe fallback to `RawCropNode(reason="table_structure_low_confidence")` (Zero Silent Loss)
  - [x] P7.T7: `src/examforge/figures/cleanup.py` — Black-border removal for photocopier scan margins
  - [x] P7.T8: Stage S6 integration (`src/examforge/stages/s6_figures.py`) with `figures_v2` feature flag and clean v1 rollback
  - [x] P7.T9: Gate 7 Verification (346/346 tests green, border-strip ink ratio == 0 for 100% crops, IoU >= 0.9 for >= 98%, zero clipped primitives, association accuracy >= 0.98, table structure accuracy >= 95%, aggregate score 1.0000 vs baseline)
- [x] **Phase 8: Restoration & Cleaning (Geometry, Illumination, Watermarks, Furniture, Branding)**
  - [x] P8.T1: `src/examforge/clean/geometry.py` — Orientation detection (0/90/180/270), projection profile variance deskew (+/- 15 deg), and two-up landscape spread splitting
  - [x] P8.T2: `src/examforge/clean/illumination.py` — Background estimation via heavy blur, flat-field division shadow flattening, and content preservation SSIM >= 0.95
  - [x] P8.T3: `src/examforge/clean/watermark_median.py` — Cross-page per-pixel median watermark estimation, flat-field division (residual correlation R03 < 0.05), moving watermark detection with fallback
  - [x] P8.T4: `src/examforge/clean/furniture.py` — Cross-page repeating furniture clustering, script-aware page number detection (Arabic, Devanagari, Roman), and question/option content protection guards
  - [x] P8.T5: `src/examforge/clean/branding.py` — URL and helpline phone scrubbing with false-positive guards (physical constants, Latin abbreviations, chemical formulas)
  - [x] P8.T6: Stage S2 integration (`src/examforge/stages/s2_clean.py`) with `clean_v2` feature flag and clean v1 rollback
  - [x] P8.T7: Gate 8 Verification (366/366 tests green, R03 < 0.05, SSIM >= 0.95, geometry sweeps +/- 15 deg and 0/90/180/270 verified, cleaning idempotency verified, aggregate score 1.0000 vs baseline)
- [x] **Phase 9: Domain Lexicons & Language Plugin Architecture**
  - [x] P9.T1: `src/examforge/lang/registry.py` & plugins (`en.py`, `hi.py`, `scaffolded.py`) — `ScriptPlugin` protocol, registry, ship-quality English/Hindi, scaffolded plugins with `NotShipQuality` warnings, `docs/ADD_A_NEW_EXAM.md`
  - [x] P9.T2: `data/fontmaps/` & `src/examforge/lang/fontmaps.py` — KrutiDev/Chanakya font mapping data, detection heuristics, and transliteration
  - [x] P9.T3: `src/examforge/lang/bilingual.py` & `src/examforge/lang/rtl.py` — N-language Unicode block segmentation honoring `language_layout`, and RTL text handling
  - [x] P9.T4: `src/examforge/notation/tokenizer.py` & `canonical.py` — Unicode math to LaTeX, Greek, operators, scientific units, vectors/hats, fractions, number/unit canonicalization
  - [x] P9.T5: `src/examforge/notation/chemistry.py` — Element symbols, charges, oxidation states, state symbols, reaction arrows, KaTeX/mhchem formatting
  - [x] P9.T6: `src/examforge/notation/wrapping.py` & `validation.py` — Token-level math wrapping, prose protection, idempotent wrapping, delimiter/brace/syntax validation, chemical equation balance (R07)
  - [x] P9.T7: Stage S5 integration (`s5_math.py`, `s5_hindi.py`) with `lang_v2` feature flag and clean v1 rollback
  - [x] P9.T8: Gate 9 Verification (464/464 tests green, 200+ notation cases, negative prose cases, multi-language synthetic documents, zero regression vs baseline)
- [x] **Phase 10: Answer Keys, Solutions & Marking Schemes**
  - [x] P10.T1: `src/examforge/answers/parse_key.py` — Multiple answer key shape parsing (inline, table, grid, separate page, Devanagari numerals, multi-correct, numeric ranges, bonus/dropped)
  - [x] P10.T2: `src/examforge/answers/bind.py` — Map keys to questions by (section, number), resolve option label schemes (1->A, क->A, etc.), attach AnswerSpec
  - [x] P10.T3: `src/examforge/answers/solutions.py` — Solution block detection and binding as list[ContentNode] reusing notation/figures
  - [x] P10.T4: `src/examforge/answers/marks.py` — Marking scheme parsing (+4/-1, partial credit) from instructions and question Marks assignment
  - [x] P10.T5: `src/examforge/validators/r16_answer_binding.py` — Rule R16 answer binding validation (referential integrity, kind compatibility, duplicate detection)
  - [x] P10.T6: Output policy & Stage integration (`s4_structure.py` / `s9_package.py`) with `answers` feature flag and clean rollback
  - [x] P10.T7: Gate 10 Verification (Synthetic keys in >=6 styles, binding accuracy >= 99%, fault injection caught by R16, marking schemes parsed, 0 regressions)
- [x] **Phase 11: Escalation Ladder & Repair (S7)**
  - [x] P11.T1: `src/examforge/confidence/calibrate.py` — Multi-signal confidence calibration (OCR, text layer, R10-R15, lexicon, geometry) with Platt scaling
  - [x] P11.T2: `src/examforge/repair/router.py` — Hierarchical repair router (T0 deterministic, T1 local rerun, T2 cheap VLM index choice, T3 JSON patch, T4 human review)
  - [x] P11.T3: `src/examforge/repair/context.py` — Minimal context builder with strict pixel & token caps
  - [x] P11.T4: `prompts/repair/<id>@<n>.md` — Versioned prompts with static prefixes for provider prompt caching
  - [x] P11.T5: `src/examforge/repair/patch.py` — Constrained JSON patch applier (RFC 6902 subset, allow-list paths, digit preservation guard, scoped validator re-run)
  - [x] P11.T6: `src/examforge/repair/gap_search.py` — Targeted gap re-search for R14 missing question numbers
  - [x] P11.T7: `src/examforge/stages/s7_repair.py` — Stage S7 integration behind `s7_repair` feature flag with clean rollback
  - [x] P11.T8: Gate 11 Verification (FakeLLM scenarios, token budget enforcement, offline fallback, zero regression)
- [x] **Phase 12: Verified Question Bank**
  - [x] P12.T1: `src/examforge/bank/store.py` — SQLite schema (`questions`, `figures`, `meta`, WAL mode, PRAGMA user_version = 1, signed/unsigned 64-bit SimHash conversion, atomic export/import JSONL, purge, stats)
  - [x] P12.T2: `src/examforge/bank/fingerprint.py` — SimHash-64 with token shingling, strict numeral & unit signatures (`compute_number_signature`), image dHash (`compute_figure_dhash`), NFC normalization and Devanagari digit mapping
  - [x] P12.T3: `src/examforge/bank/match.py` — Multi-stage matcher with strict invariance (differing numerals/units or option counts strictly block `EXACT_REUSE`, emit `NEAR_HINT` warning)
  - [x] P12.T4: `src/examforge/bank/ingest.py` & CLI (`examforge bank stats|purge|export|import`) — Ingestion pipeline computing content hashes with verified audit metadata
  - [x] P12.T5: Stage S4 reuse path (`src/examforge/stages/s4_structure.py`) — Feature flag `bank` gating exact 0-token reuse with `Provenance.BANK` and `confidence=1.0`
  - [x] P12.T6: `src/examforge/bank/embeddings.py` — Abstract `EmbeddingModel` protocol and zero-cost `DisabledEmbeddingModel` default
  - [x] P12.T7: Gate 12 Verification (21/21 tests green, SimHash distribution over 1,000 pairs, 10,000 single-token mutation false-reuse safety suite, thread pool concurrency, E2E second-run zero-token reuse)
- [x] **Phase 13: Auto-Profiling & Scaffolding (S1)**
  - [x] P13.1: `src/examforge/profiles/fingerprint.py` — Consensus structural fingerprinting (gutters, header band hash, Unicode script distribution, numbering & option signals) and WAL-mode SQLite cache (`profile_cache.sqlite`)
  - [x] P13.2: `src/examforge/profiles/infer_rules.py` — Deterministic inference of scripts, language layout (`monolingual`, `parallel_columns`, `interleaved`), columns, numbering regexes, option schemes, and per-field confidence scoring
  - [x] P13.3: `src/examforge/profiles/infer_llm.py` — One-shot LLM profile completion for fields below threshold with regex catastrophic backtracking / ReDoS safety guards and graceful review fallback
  - [x] P13.4: `src/examforge/profiles/scaffold.py` — Profile scaffolding generator emitting YAML draft specifications and visual debug overlays (`profile_preview.html`)
  - [x] P13.5: Proposal persistence in `profiles/learned/<id>.yaml` with `maturity: experimental`
  - [x] P13.6: Stage S1 Profile (`src/examforge/stages/s1_profile.py`) and CLI integration (`examforge profile scaffold`, `--profile auto`)
  - [x] P13.7: Gate 13 Verification (19/19 tests green, fingerprint stability under noise >= 0.95 and cross-family distinctness, deterministic inference accuracy, FakeLLM safety suite, cache hit zero-token guarantee)
- [x] **Phase 14: Template v2 & Exporters**
  - [x] P14.1: `src/examforge/templates/exam_v2.html.j2` — Template v2 with macros for 9 `ContentNode` kinds (`text`, `math`, `table`, `figure`, `statements`, `match_columns`, `code`, `blank`, `raw_crop`), subparts, passages, answer keys, solutions, and intelligent greedy option packing (`opt-col-1`, `opt-grid-2`, `opt-grid-4`)
  - [x] P14.2: Layout modes — `bilingual_parallel` (CSS grid row per question), `monolingual`, `stacked` with continuous flow, serial numbers in gutters, per-column `lang` & `dir` attributes
  - [x] P14.3: Print CSS — `@media print`, `@page` margins, `break-inside: avoid` per question, no running headers/footers
  - [x] P14.4: Self-contained assets & strict offline CSP meta forbidding external loads
  - [x] P14.5: Accessibility & determinism — semantic landmarks, figure alt texts, stable IDs, byte-identical double render
  - [x] P14.6: Exporters (`src/examforge/export/`) — `HTMLExporter`, `JSONExporter`, `MarkdownExporter`, `JSONLExporter`, `QTIExporter` (QTI-lite XML with sidecar `qti_unsupported.json`), and `ExporterRegistry`
  - [x] P14.7: Template selection & S9 Package integration behind `template_v2` and `exporters` feature flags with clean v1 rollback
  - [x] P14.8: Gate 14 Verification (12/12 tests green, offline CSP assertion, determinism proof, all exporters valid, v1 characterization preserved)
- [x] **Phase 15: Self-Improving Loop**
  - [x] P15.1: `src/examforge/lessons/store.py` — Append-only JSONL storage with file locking, canonical signature normalization (`normalize_issue_signature`), schema validation, corrupt-line tolerance, and compaction
  - [x] P15.2: Recording hooks — Automated recording hook in `s7_repair.py` triggered upon validated LLM patch under `lessons` feature flag
  - [x] P15.3: `src/examforge/lessons/retrieve.py` — BM25-style scoring with exact stage/rule matching, context features boosting, and strict token budget enforcement
  - [x] P15.4: `src/examforge/lessons/promote.py` — Threshold detection (recurrence >= 3, papers >= 2) emitting markdown proposals (`proposals/<id>.md`) with generated failing tests and draft rule scaffolds without modifying production code
  - [x] P15.5: Rule promotion & retirement lifecycle — Retiring promoted lessons to shrink prompts and context footprint
  - [x] P15.6: CLI commands in `src/examforge/cli.py` (`examforge lessons list|promote|compact`)
  - [x] P15.7: Gate 15 Verification (11/11 tests green, 0-token lesson reuse, recording hook on fresh patch, clean rollback on `lessons: False`, full promotion dry run, context shrink)
- [x] **Phase 16: Orchestrator, CLI & Plugin Hardening**
  - [x] P16.1: `src/examforge/orchestrator/dag.py` — Formal Stage DAG with topological sort, cycle detection, selective stage execution (`--from-stage`, `--to-stage`, `--only`), and checkpoint state hashing
  - [x] P16.2: `src/examforge/orchestrator/io.py` — Atomic I/O writes with `fsync`, cross-platform exclusive run locking (`RunLock`), run ID sanitization against path traversal, timestamped run directories, append-only `events.jsonl` logger
  - [x] P16.3: `src/examforge/orchestrator/robustness.py` — Input robustness preflight with `EncryptedPDFError`, `CorruptPDFError`, `ImageBombError` (50MP ceiling), ZIP/directory unpacker, test PDF tolerance
  - [x] P16.4: `src/examforge/orchestrator/plugins.py` — Plugin lifecycle manager, entrypoint + directory discovery, `api_version` compatibility checks, isolated execution wrapper with error capture
  - [x] P16.5: `src/examforge/orchestrator/logging.py` — Structured JSON logging formatter with automated redaction of sensitive credentials, tokens, and API keys
  - [x] P16.6: Runner & CLI hardening — Runner integration with DAG, atomic manifest writing, `examforge doctor`, `examforge plugins list`, `examforge schema`, `--json` output
  - [x] P16.7: Gate 16 Verification (22/22 runner & orchestrator tests green, DAG cycle detection, stage slicing, crash recovery / atomic replace, input bomb rejection, plugin isolation, structured event logging)
- [x] **Phase 17: Acceptance, Flag Flips & Release**
  - [x] P17.1: Full evaluation & baseline verification
  - [x] P17.2: Feature flag flips (`verifiers_v2`, `layout_v2`, `figures_v2`, `clean_v2`, `lang_v2`, `answers`, `s7_repair`, `bank`, `autoprofile`, `lessons`, `template_v2`, `exporters` all default `True` in `ExamForgeConfig` and `examforge.yaml`)
  - [x] P17.3: Package metadata and version release bump to `2.0.0` in `__init__.py` and `pyproject.toml`
  - [x] P17.4: CLI operational command hardening: `execute <paper>` with positional argument support and `--profile auto` default
  - [x] P17.5: Comprehensive v2 documentation suite (`README.md`, `ARCHITECTURE.md`, `PROFILE_GUIDE.md`, `RUNBOOK.md`, `TESTING.md`, `TOKEN_BUDGET.md`, `PERF.md`, `docs/MIGRATION_V1_V2.md`, `CHANGELOG.md`, `metrics/RELEASE_REPORT.md`)
  - [x] P17.6: `review.html` and exit code 20 (`EXIT_NEEDS_REVIEW`) alignment in `PipelineRunner`
  - [x] P17.7: Gate 17 Acceptance Verification (`tests/test_gate17_acceptance.py` 5/5 passed, 0 regressions)

---

## Optimization Program (EXAMFORGE_OPTIMISATION_PLAN.md)

- [x] **Phase O0: Measurement, Profiling & Baseline (Mandatory)**
  - [x] O0.1: Profiling baseline and hypothesis confirmation (`docs/PROFILE_REPORT.md` confirming H1–H10)
  - [x] O0.2: Oracle-stage attribution harness (`src/examforge/eval/oracle.py` + `examforge eval --oracle <stage>`)
  - [x] O0.3: Error taxonomy & stage snapshot diffing tool (`src/examforge/eval/taxonomy.py` + `docs/ERROR_TAXONOMY.md`)
  - [x] O0.4: Redundancy & dead weight audit (`docs/REDUNDANCY_AUDIT.md`)
  - [x] Gate O0 Verification (`tests/test_phase_o0_measurement.py`: 6/6 tests green in 1.63s, all 4 reports committed)
- [x] **Phase O1: Zero-Behavior-Change Quick Wins**
- [x] **Phase O2: Digital-First Fast Path**
  - [x] O2.1: Page processing path classifier (`_classify_processing_path` distinguishing Path A digital, Path B scan, Path C broken font)
  - [x] O2.2: Path A direct PyMuPDF text block extraction with zero model inference (`PaddleVLAdapter.get_inference_count() == 0`) and sub/superscript baseline reconstruction
  - [x] O2.3: Path B selective PaddleOCR-VL-1.6 inference for scans and raster pages
  - [x] O2.4: Path C glyph-level decoding (`GlyphDecoder`) with persistent process cache (0 OCR calls on repeated fonts)
  - [x] O2.5: Second engine on demand selective check for low-confidence blocks
  - [x] O2.6: Early exit skipping non-question pages (`COVER`, `INSTRUCTIONS`, `ROUGH_WORK`, `BLANK`, `OMR`)
  - [x] Gate O2 Verification (`tests/test_phase_o2_digital_first.py`: 5/5 tests green in 0.24s, all 41 test suite tests pass)
- [x] **Phase O3: Reorder and Merge Stages**
  - [x] O3.1: Canonical DAG re-ordered: S0 Probe → S1 Profile → S2 Clean → S3 Parse → S4 Structure → S5 Normalize → S6 Figures → S8 Verify → S7 Repair → S9 Package
  - [x] O3.2: Cheap profiling input using direct PDF text layer when blocks are not yet parsed
  - [x] O3.3: Conditional cleaning with skip tracking & coordinate lock (geometry_final)
  - [x] O3.4: Unified S5 Normalize combining math and Hindi into single question walk
  - [x] O3.5: Backwards compatible stage aliases (s5_math, s5_hindi -> s5_normalize)
  - [x] O3.6: Do-No-Harm invariant (multiset digit and scientific unit preservation)
  - [x] Gate O3 Verification (`tests/test_phase_o3_reorder_merge.py`: 6/6 tests green in 0.40s, 33/33 total suite pass)
- [x] **Phase O4: Validator Consolidation and Cost Tiers**
  - [x] O4.1: Cost tiers (FREE, IO, HEAVY) assigned across all validators and gated in S8
  - [x] O4.2: Merged overlapping rules (furniture_branding, language_consistency, structure_integrity, packaged_output_check) with transparent alias resolution
  - [x] O4.3: Incremental verify (verify_question) scoped to target question after repair
  - [x] O4.4: Precision audit & WARN gating (WARN never triggers repair in S7)
  - [x] O4.5: Capability / profile gating (skips bilingual checks on monolingual documents)
  - [x] Gate O4 Verification (`tests/test_phase_o4_validators.py`: 5/5 tests green in 0.37s, `tests/faults/test_fault_injection.py`: 19/19 green in 11.46s, `tests/test_validators.py`: 10/10 green in 0.14s)
- [x] **Phase O5: Repair Safety and Token Guardrails**
  - [x] O5.1: Net-benefit ledger (NetBenefitLedger) recording validators before/after, accept/revert, auto-disabling harmful tiers
  - [x] O5.2: LLM-eligible issues only (BLOCKER severity + localized bounds + candidates/text) and per-paper repair cap
  - [x] O5.3: Preference for local tiers (T0/T1) before model escalation
  - [x] O5.4: Per-paper token budget enforcement halting repairs with exit code 20 and review.html
  - [x] O5.5: Harm guard enforcing repair harm rate <= 0.1%, digit-preserving invariant, and patch allow-list
  - [x] Gate O5 Verification (`tests/test_phase_o5_repair_safety.py`: 5/5 tests green in 1.01s, `tests/test_s7_repair.py`: 4/4 green, `tests/test_gate11_verification.py`: 8/8 green)
- [x] **Phase O6: Delete Dead Weight and Consolidate**
  - [x] O6.1: Unified generic `Registry[T]` backing `ValidatorRegistry`, `LanguageRegistry`, `ExporterRegistry`
  - [x] O6.2: Compute tier consolidation (`ExamForgeConfig.compute_tier` linked to `profiles/compute.py`)
  - [x] O6.3: Lazy-loading non-core exporters (`markdown`, `jsonl`, `qti`) and scaffolded language plugins
  - [x] O6.4: Stage wrapper thinness and duplicate code cleanup
  - [x] Gate O6 Verification (`tests/test_phase_o6_consolidation.py`: 3/3 tests green in 0.12s, 38/38 phase suite tests pass)
- [x] **Phase O7: Accuracy Hardening on Real Data**
  - [x] O7.1: Edit budget enforcement in S5 Normalize (reverts text and emits warning if edit ratio exceeds threshold)
  - [x] O7.2: Real gold set evaluation and synthetic-vs-real gap bounds
  - [x] O7.3: Transformation whitelists (multiset digit and scientific unit preservation, S2 subpart protection)
  - [x] O7.4: Targeted accuracy techniques (Devanagari syllable grammar, canonical boilerplate snapping, vertical baseline figure ordering, option homogeneity)
  - [x] O7.5: Conservative defaults preserving original input on low-confidence transformations
  - [x] Gate O7 Verification (`tests/test_phase_o7_accuracy_hardening.py`: 8/8 tests green in 0.39s, 46/46 phase suite tests pass)
- [x] **Phase O8: Re-Benchmark, Ratchet, Document**
  - [x] O8.1: Full evaluation vs O0 baseline (`docs/PERF.md` with complete before/after comparison table)
  - [x] O8.2: CI performance ratchet guard (`src/examforge/perf/ratchet.py` enforcing <=10% timing/RSS and <=0.5pp accuracy regression limits)
  - [x] O8.3: Monotonic ratchet forward tightening (`make ratchet` / `tighten_ratchet`)
  - [x] O8.4: Documentation updated: `ARCHITECTURE.md` (canonical DAG, digital-first multi-path architecture), `RUNBOOK.md` (`--checkpoint`, ratchet guide), `docs/PERF.md`
  - [x] Gate O8 Verification (`tests/test_phase_o8_ratchet_benchmark.py`: 7/7 tests green in 0.14s, 53/53 optimization suite green in 2.67s)

---

## Gate Log

| Gate | Status | Date | Evidence |
|---|---|---|---|
| Gate 0 | PASSED | 2026-10-12 | 158/158 tests green (19.54s), network socket blocker active, RECON/BLOCKERS/DEPENDENCIES established |
| Gate 1 | PASSED | 2026-10-12 | 178/178 tests green (17.41s), telemetry ledger + LLM boundary isolated, token budget + cache + fake + cassette replay verified, AST provider isolation enforced |
| Gate 2 | PASSED | 2026-10-13 | 194/194 tests green (31.59s), ContentNode discriminated union, v1-v2 migrator & loader verified, strict invariants system active, schemas/examdocument.v2.json exported, E2E characterization 25/25 Qs verified |
| Gate 3 | PASSED | 2026-10-13 | 224/224 tests green (28.67s), 10 profiles validated, AST no-hardcoding guard active, capability negotiation + compute tiers + spec_hash invalidation verified, golden JEE + NEET characterization (25/25 Qs) verified |
| Gate 4 | PASSED | 2026-10-13 | 248/248 tests green (28.69s), 21 universal families generated, CER/WER/IoU/TEDS metrics + ExamScorer active, baseline captured (metrics/baseline.json), thresholds calibrated (metrics/thresholds.yaml), docs/BASELINE.md committed |
| Gate 5 | PASSED | 2026-10-13 | 267/267 tests green (19.52s), 100% fault detection across 70 mutators, 0 false-positive blockers on clean seeds, 200 questions evaluated in <0.2s, characterization 25/25 Qs identical |
| Gate 6 | PASSED | 2026-10-13 | 317/317 tests green (25.37s), 0 regressions vs baseline (aggregate score 1.0000), ReDoS safe on 100KB inputs, layout_v2 feature flag active with v1 rollback |
| Gate 7 | PASSED | 2026-10-13 | 346/346 tests green (35.38s), border-strip ink ratio == 0 for 100% crops, IoU >= 0.9 for >= 98%, zero clipped primitives, association accuracy >= 0.98, table structure accuracy >= 95% with Zero Silent Loss, figures_v2 flag with clean v1 rollback |
| Gate 8 | PASSED | 2026-10-13 | 366/366 tests green (40.80s), residual correlation R03 < 0.05, SSIM >= 0.95 over content mask, geometry sweeps +/- 15 deg and 0/90/180/270, script-aware page numbers, branding guards for scientific constants, clean_v2 flag with clean v1 rollback |
| Gate 9 | PASSED | 2026-10-13 | 464/464 tests green (50.67s), 200+ notation cases verified, negative prose cases strictly preserved (x, 2, m unwrapped), wrapping idempotent, KrutiDev/Chanakya font maps, 3-language and RTL splitting verified, lang_v2 flag with clean v1 rollback, 0 regressions vs baseline (score 1.0000) |
| Gate 10 | PASSED | 2026-10-13 | 512/512 tests green (99.19s), synthetic keys in >= 6 styles, binding accuracy >= 99% (100/100 Qs), fault injection caught by R16, marking schemes parsed across English/Hindi/mixed phrasing, solutions with math/figures, include_answers: false default policy verified, answers flag with clean rollback, 0 regressions vs baseline (aggregate score 1.0000) |
| Gate 11 | PASSED | 2026-10-14 | 30/30 tests green (2.87s), Platt scaling confidence calibration, T0-T4 escalation router, minimal context builder (hard token/pixel caps), constrained JSON patch applier with digit preservation guard, gap re-search, FakeLLM hostile suite, offline fallback (exit 20 + review.html), LLM-touched <= 15%, 0 regressions |
| Gate 12 | PASSED | 2026-10-14 | 21/21 tests green (31.95s), SimHash-64 distribution, 10,000 single-token mutation false-reuse safety (0 false reuses), SQLite threadpool multi-writer concurrency, 100% E2E 0-token question reuse |
| Gate 13 | PASSED | 2026-10-14 | 19/19 tests green (2.23s), fingerprint stability under noise >= 0.95 and distinctness across families, deterministic inference accuracy >= 0.95, FakeLLM ReDoS/backtracking regex safety guard, cache hit zero tokens, visual overlay preview generator |
| Gate 14 | PASSED | 2026-10-14 | 12/12 tests green (2.01s), template_v2 Jinja2 macros covering 9 ContentNode kinds, greedy option packing, bilingual_parallel/monolingual/stacked layouts, strict offline CSP forbidding external loads, byte-identical double render determinism, schema-compliant JSON/Markdown/JSONL/QTI-lite exporters with unsupported sidecar report, exact v1 characterization rollback |
| Gate 15 | PASSED | 2026-10-14 | 11/11 tests green (0.83s), 0-token repair via lesson retrieval, automatic patch recording hook, clean rollback when lessons: false, full promotion dry run (record -> recurrence -> propose -> implement -> retire -> shrink context), CLI lessons list/promote/compact verified |
| Gate 16 | PASSED | 2026-10-14 | 22/22 tests green (3.42s), DAG cycle detection, slice execution (--from-stage/--to-stage/--only), atomic write + crash consistency, 50MP image bomb & encrypted PDF rejection, plugin crash isolation, structured event log + secret redaction, examforge doctor/plugins/schema CLI |
| Gate 17 | PASSED | 2026-10-14 | 5/5 acceptance tests green (12.20s), all 12 feature flags flipped to True, v2.0.0 metadata bumped, execute <paper> positional argument & --profile auto verified, full pipeline E2E with template v2 & all exporters active, review.html and exit code 20 verified |
| Gate O0 | PASSED | 2026-10-14 | 6/6 tests green (1.63s), PROFILE_REPORT.md (H1–H10 confirmed), ERROR_TAXONOMY.md (85 defects categorized), REDUNDANCY_AUDIT.md (5 registries, dead code), oracle attribution harness active |
| Gate O1 | PASSED | 2026-10-14 | 8/8 tests green (0.54s), process-level warm engine caching, central thread budget clamping, render-once uint8 pixmap cache, downsampled background estimators (1/8 scale), spatial grid clustering, checkpoint tiers (major/all/none), load-time ReDoS regex vetting |
| Gate O2 | PASSED | 2026-10-14 | 5/5 tests green (0.24s), path classifier (A/B/C), Path A zero model inference (assert 0), sub/superscript baseline reconstruction, Path C GlyphDecoder font caching, early exit skipping non-question pages |
| Gate O3 | PASSED | 2026-10-14 | 6/6 tests green (0.40s), canonical DAG reordered (S2 before S3, S8 before S7), cheap profiling from PDF text, conditional clean skip tracking + geometry_final, unified S5 Normalize with Do-No-Harm multiset preservation, backward-compatible aliases |
| Gate O4 | PASSED | 2026-10-14 | 5/5 tests green (0.37s), 19/19 fault injection green (11.46s), 10/10 validator tests green (0.14s), consolidated rules (R01+R02, R05+R10, R06+R14+R15, R04+R13), cost tiers (FREE/IO/HEAVY), incremental verify_question, WARN never triggers repair |
| Gate O5 | PASSED | 2026-10-14 | 5/5 tests green (1.01s), 8/8 Gate 11 green (0.74s), 4/4 S7 green (0.35s), net-benefit ledger, auto-disabling non-beneficial tiers, LLM eligibility gating, per-paper caps & token budgets, harm rate <= 0.1% |
| Gate O6 | PASSED | 2026-10-14 | 3/3 tests green (0.12s), 38/38 phase suite green, generic Registry[T] consolidation, unified compute tier config, lazy-loaded exporters and scaffolded lang plugins |
| Gate O7 | PASSED | 2026-10-14 | 8/8 tests green (0.39s), 46/46 phase suite green, edit budget rollback, digit & unit whitelists, subpart protection, Devanagari syllable grammar, boilerplate snapping, vertical baseline figure ordering, option homogeneity |
| Gate O8 | PASSED | 2026-10-14 | 7/7 tests green (0.14s), 53/53 full optimization suite green (2.67s), docs/PERF.md benchmarks verified, CI performance ratchet guard active, ARCHITECTURE.md and RUNBOOK.md fully updated |









