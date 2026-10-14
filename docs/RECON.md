# ExamForge v2 — Reconciliation & Repository Mapping (Phase 0 Recon)

**Date:** 2026-10-12  
**Baseline Test Status:** 157/157 passing tests (100%)  
**Python Version:** Python 3.14 (requires-python >= 3.11)  
**Package Manager / Build:** Hatchling (`pyproject.toml`)  

---

## 1. Spec Module to Repository Mapping

Per the **Reconciliation Rule**, existing module locations are mapped below without unnecessary renames:

| Target Spec Module | Actual Repository Location | Status | Notes |
|---|---|---|---|
| `runner.py` | [`src/examforge/orchestrator/runner.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/orchestrator/runner.py) | ✅ Present | Sequential runner with `--resume`, manifest tracking, checkpoints |
| `manifest.py` | [`src/examforge/orchestrator/manifest.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/orchestrator/manifest.py) | ✅ Present | Run manifest & stage records |
| `schema.py` | [`src/examforge/ir/schema.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/ir/schema.py) | ✅ Present | Pydantic v2 IR (`ExamDocument`, `Block`, `Question`, `Option`, `Figure`) |
| `spec.py` | [`src/examforge/spec.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/spec.py) | ✅ Present | Declarative rules R01–R09 with SHA-256 spec hash |
| `config.py` | [`src/examforge/config.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/config.py) | ✅ Present | Layered config (`ExamForgeConfig`) via pydantic-settings |
| `cli.py` | [`src/examforge/cli.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/cli.py) | ✅ Present | CLI commands: `execute`, `resume`, `inspect` |
| `s0_intake.py` | [`src/examforge/stages/s0_intake.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s0_intake.py) | ✅ Present | Render, classification, DPI, legacy fonts |
| `s2_clean.py` | [`src/examforge/stages/s2_clean.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s2_clean.py) | ✅ Present | Repeating furniture, watermarks, branding |
| `s3_parse.py` | [`src/examforge/stages/s3_parse.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s3_parse.py) | ✅ Present | Digital PyMuPDF text layer + Paddle-VL-1.6 adapter |
| `s4_structure.py` | [`src/examforge/stages/s4_structure.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s4_structure.py) | ✅ Present | Column-aware sorting, question segmentation, option parsing |
| `s5_math.py` | [`src/examforge/stages/s5_math.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s5_math.py) | ✅ Present | Unicode math to LaTeX, token math wrapping |
| `s5_hindi.py` | [`src/examforge/stages/s5_hindi.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s5_hindi.py) | ✅ Present | Devanagari NFC, danda conversion, interleaved bilingual split |
| `s6_figures.py` | [`src/examforge/stages/s6_figures.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s6_figures.py) | ✅ Present | Crop extraction, multi-block & proportional assignment |
| `s8_verify.py` | [`src/examforge/stages/s8_verify.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s8_verify.py) | ✅ Present | R01–R09 validators execution, fail_fast support |
| `s9_package.py` | [`src/examforge/stages/s9_package.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/stages/s9_package.py) | ✅ Present | Offline HTML packaging, base64 embedding |
| `exam.html.j2` | [`src/examforge/templates/exam.html.j2`](file:///c:/Users/D.Solanki/pipeline/src/examforge/templates/exam.html.j2) | ✅ Present | 50/50 dual column continuous NEET layout |
| `validators/` | [`src/examforge/validators/`](file:///c:/Users/D.Solanki/pipeline/src/examforge/validators/) | ✅ Present | Validators R01 through R09 + registry |
| `paddle_vl.py` | [`src/examforge/engines/paddle_vl.py`](file:///c:/Users/D.Solanki/pipeline/src/examforge/engines/paddle_vl.py) | ✅ Present | Paddle-VL-1.6 adapter with half-open circuit breaker |

---

## 2. Planned Target Modules (To Be Created in Upcoming Phases)

- **Phase 1**: `src/examforge/telemetry.py`, `src/examforge/llm/` (`types.py`, `client.py`, `fake.py`, `recording.py`, `budget.py`, `cache.py`)
- **Phase 2**: `src/examforge/invariants.py`, IR schema v2 migrator
- **Phase 3**: `src/examforge/profiles/` (`schema.py`, `loader.py`, `builtin/*.yaml`, `fingerprint.py`)
- **Phase 4**: `src/examforge/synth/` (generator, degrade, fonts, corpora), `src/examforge/eval/` (metrics, scorer, compare)
- **Phase 5**: `src/examforge/validators/` (expanding to R01–R14, including free bilingual cross-verification & text-layer token diff)
- **Phase 6**: `src/examforge/layout/` (columns, reading order, passages)
- **Phase 7**: `src/examforge/figures/` (vector-first SVG extraction, grow-until-clean ink border)
- **Phase 8**: `src/examforge/clean/` (per-pixel median watermark estimator, deterministic subtraction)
- **Phase 9**: `src/examforge/math/` & `src/examforge/lang/` (domain lexicons, chemistry, units, language plugins)
- **Phase 10**: `src/examforge/repair/` (repair ladder T0-T4, multiple-choice framing)
- **Phase 11**: `src/examforge/bank/` (verified question bank, fingerprint, matching)
- **Phase 12**: S1 Profile stage integration
- **Phase 13**: `src/examforge/templates/exam_v2.html.j2`
- **Phase 14**: `src/examforge/lessons/` (lessons store, retrieval, promotion)
- **Phase 15**: CLI hardening & universal batch runner
- **Phase 16**: Feature flag flips & end-to-end evaluation

---

## 3. Environment & Test Baseline

- **Current passing tests:** 157
- **Test execution time:** ~14 seconds
- **Core dependencies installed:** `click`, `pydantic`, `pydantic-settings`, `pyyaml`, `pymupdf`, `pillow`, `numpy`, `jinja2`, `pytest`
- **Socket policy:** Enforce autouse fixture blocking network sockets in tests unless explicitly marked `@pytest.mark.network`.
