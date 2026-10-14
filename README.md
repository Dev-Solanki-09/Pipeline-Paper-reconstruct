# ExamForge v2.0

**ExamForge** is an autonomous, token-efficient, universal exam paper reconstruction engine. It converts raw, scanned, degraded, or digital Indian competitive exam papers (NEET-UG, JEE Main/Advanced, UPSC, GATE, State Boards) into clean, printable, accessible bilingual HTML documents and multi-format data artifacts — with KaTeX math, chemical formulas, vector diagrams, table extraction, and strict automated invariants.

---

## Key Features

1. **Token-Efficient Autonomous Pipeline**
   - **>74% token reduction** via deterministic verifiers (R01–R16), STEM lexicons, and the T0–T4 escalation ladder.
   - LLM calls needed on only **~6% of questions**; 0 tokens on repeated papers via SimHash-64 bank matching.
2. **Universal Exam Profiles & Auto-Profiling**
   - Ingests unseen exams automatically with `--profile auto`. Consensus fingerprinting extracts columns, scripts, and numbering rules on the fly.
3. **Rich Intermediate Representation (IR v2)**
   - Discriminated union `ContentNode` model supporting text, math (KaTeX/mhchem), vector diagrams, reconstructed tables, statements, match-the-columns, code, and blanks.
4. **Vector-First Figure & Table Pipeline**
   - Direct extraction of PDF vector paths with grow-until-clean crop refinement and zero silent loss table fallback.
5. **Restoration & Watermark Median Scrubbing**
   - Automatic deskew (+/- 15°), flat-field illumination correction, cross-page median watermark scrubbing, and script-aware page numbering.
6. **Multi-Format Exporters**
   - Emits single-file standalone HTML (offline CSP), IR JSON, Markdown, streaming JSONL, and IMS QTI XML.

---

## Quick Start

### Installation

```bash
# Clone and create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows (or source .venv/bin/activate on Unix)

# Install dependencies
pip install -e ".[dev]"
```

### Ingesting an Exam Paper

```bash
# Process any exam paper immediately (auto-profile enabled by default)
examforge execute paper.pdf

# Specify compute tier for low-memory environments
examforge execute paper.pdf --compute lite

# Export custom formats
examforge execute paper.pdf --profile neet_ug --json
```

### Diagnostics & Inspection

```bash
# Inspect system dependencies and OCR capabilities
examforge doctor

# List discovered plugins
examforge plugins list

# Inspect completed run manifest
examforge inspect --run-id <run_id>
```

---

## Exit Codes

| Code | Status | Meaning |
|:----:|:-------|:--------|
| **0** | `EXIT_OK` | All validation rules pass. Complete output ready in `runs/<run_id>/output.html`. |
| **10** | `EXIT_WARNINGS` | Completed with non-blocking warnings. Output is valid. |
| **20** | `EXIT_NEEDS_REVIEW` | Disputed blocks or escalated repairs require human sign-off via `runs/<run_id>/review.html`. |
| **30** | `EXIT_FAILED` | Pipeline halted due to unhandled error, corrupt PDF, or invariant blocker. |

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — System topology, DAG stages, and IR schema reference.
- [RUNBOOK.md](RUNBOOK.md) — Operational runbook for executing papers and processing reviews.
- [PROFILE_GUIDE.md](PROFILE_GUIDE.md) — Declarative YAML exam profile specifications and scaffolding.
- [TOKEN_BUDGET.md](TOKEN_BUDGET.md) — Token accounting, budget governor, and cache management.
- [PERF.md](PERF.md) — Compute tiers (`lite`, `standard`, `gpu`) and resource guidelines.
- [TESTING.md](TESTING.md) — Zero-regression test philosophy and quality gates.
- [docs/MIGRATION_V1_V2.md](docs/MIGRATION_V1_V2.md) — Migration guide from v1 to v2.
- [CHANGELOG.md](CHANGELOG.md) — v2.0.0 release changelog.
- [metrics/RELEASE_REPORT.md](metrics/RELEASE_REPORT.md) — Benchmark metrics and gate logs.
