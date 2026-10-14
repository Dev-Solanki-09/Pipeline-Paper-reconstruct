# ExamForge v2.0 Operational Runbook

This runbook describes standard operating procedures for processing exam papers with ExamForge v2.0.

---

## 1. Quick Start: Operating Exam Papers

### Standard Ingestion Command
To process any exam paper (digital PDF or scan), run:

```bash
examforge execute <path_to_paper.pdf>
```

- **Zero configuration required**: `--profile auto` is enabled by default.
- **Fingerprinting & Caching**: S1 Profile checks `data/profiles/profile_cache.sqlite` by document header hash, script ratios, and column geometry.
- **Zero tokens on known shapes**: If a paper matches an existing verified profile, it reuses the profile instantly with zero LLM queries.
- **Unseen exams**: Automatically infers layout, column structure, numbering schemes, and option patterns, generating a proposal under `profiles/learned/`.

### Options & Flags

| Flag | Description | Default |
|---|---|---|
| `<paper>` | Path to the exam PDF file (positional argument) | *Required* |
| `-p, --profile <id>` | Explicit profile override (`neet_ug`, `jee_main`, `gate`, etc.) | `auto` |
| `-m, --mode <mode>` | `fast` (single engine) or `max` (dual engine) | `fast` |
| `-c, --compute <tier>` | Compute tier: `lite` (low RAM), `standard`, or `gpu` | `standard` |
| `--checkpoint <tier>` | Checkpoint tier: `major` (default, low I/O), `all`, or `none` | `major` |
| `--debug` | Include provenance attributes and visual debug overlays in HTML | `false` |
| `--json` | Output execution summary as machine-readable JSON | `false` |
| `--from-stage <s_id>` | Start execution from specified pipeline stage | *None* |
| `--to-stage <s_id>` | Halt execution after specified pipeline stage | *None* |
| `--only <s_id>` | Execute only the specified stage | *None* |

---

## 2. Exit Code Semantics

ExamForge CLI commands exit with strict, actionable status codes:

| Exit Code | Status | Meaning & Operator Action |
|---|---|---|
| **0** | `EXIT_OK` | **Pass**. All invariants and validation rules passed. Output ready in `runs/<run_id>/output.html`. |
| **10** | `EXIT_WARNINGS` | **Pass with warnings**. Non-critical issues detected (e.g. minor OCR confidence dip, non-blocking typo). Output is valid and printable. |
| **20** | `EXIT_NEEDS_REVIEW` | **Human review required**. The pipeline encountered an ambiguous ambiguity or model patch reached T4 escalation. Open `runs/<run_id>/review.html` to review flagged questions. |
| **30** | `EXIT_FAILED` | **Failure**. Unrecoverable error (e.g. corrupt/encrypted input, unresolvable invariant blocker). Check `runs/<run_id>/events.jsonl` and console error output. |

---

## 3. Human Review & Lesson Feedback Loop

When a run exits with code **20**:
1. Open `runs/<run_id>/review.html` in your browser.
2. Review the defective question and the corresponding image crop.
3. If an OCR typo or option binding is corrected manually, record the lesson:
   ```bash
   examforge lessons list
   examforge lessons promote
   ```
4. The lessons store (`data/lessons/lessons.jsonl`) captures the canonical error signature and solution. Subsequent runs encountering the same error pattern will automatically resolve it at T0 (zero tokens) without human intervention!

---

## 4. Run Outputs & Artifacts

Each run generates an isolated, timestamped run directory under `runs/<run_id>/`:
- `manifest.json`: Complete run manifest, stage timing, RSS memory, and token counters.
- `document.json`: The authoritative Intermediate Representation (IR v2) in JSON format.
- `output.html`: Single-file, standalone, offline-secure HTML rendition formatted according to exam profile.
- `output.md`: Markdown export with KaTeX notation.
- `questions.jsonl`: Line-delimited JSON stream of questions for question banks.
- `qti.xml`: IMS QTI-compliant export package.
- `events.jsonl`: Audit log of stage transitions and metrics.
- `review.html`: (Generated only on exit code 20) visual card deck for flagged items.

---

## 5. Performance Verification & CI Ratchet Guard

Check performance targets against baseline:
```bash
python -m examforge.perf.ratchet
```

Ratchet forward performance targets when optimizations improve timing or RSS:
```bash
make ratchet
```

---

## 6. Maintenance & Diagnostics

Check environment and dependencies:
```bash
examforge doctor
```

List loaded and discovered plugins:
```bash
examforge plugins list
```

Export schema definition:
```bash
examforge schema export -o schemas/examdocument.v2.json
```

Manage question bank cache:
```bash
examforge bank stats
examforge bank purge --days 30
```
