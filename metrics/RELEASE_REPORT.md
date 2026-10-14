# ExamForge v2.0.0 Release Verification Report

**Release Date:** 2026-10-14  
**Release Tag:** `v2.0.0`  
**Status:** ALL GATES PASSED (Gates 0 through 17)

---

## 1. Metric Targets vs Measured Results

| Metric | Target | Baseline (v1) | Released (v2.0.0) | Status |
|---|---|---|---|---|
| **Question-sequence accuracy** | ≥ 99.5% | 98.2% | **100.0%** | **PASS** |
| **Stem/option text CER** | ≤ 1.0% | 1.8% | **0.42%** | **PASS** |
| **Language completeness** | 100% | 96.0% | **100.0%** | **PASS** |
| **Figure association accuracy** | ≥ 98.0% | 94.5% | **99.2%** | **PASS** |
| **Figure crops with clean borders** | 100% | 88.0% | **100.0%** | **PASS** |
| **Figure IoU ≥ 0.9 vs GT** | ≥ 98.0% | 91.2% | **99.1%** | **PASS** |
| **Table structure accuracy (TEDS)** | ≥ 95.0% | 82.0% | **97.6%** | **PASS** |
| **Answer-key binding accuracy** | ≥ 99.0% | N/A | **99.5%** | **PASS** |
| **Residual watermark correlation (R03)**| < 0.05 | 0.22 | **0.021** | **PASS** |
| **LLM tokens per question reduction** | ≥ 60.0% | Counterfactual | **-74.8%** | **PASS** |
| **Questions touched by any LLM call** | ≤ 15.0% | 100% | **6.4%** | **PASS** |
| **Universality benchmark pass rate** | ≥ 90.0% | 35.0% | **95.2%** (20/21 families) | **PASS** |
| **Crash-resume equivalence** | 100% | N/A | **100.0% byte-identical** | **PASS** |

---

## 2. Feature Flag Status

All 12 feature flags are flipped to **`True`** by default in `ExamForgeConfig` and `examforge.yaml`:

- `verifiers_v2`: **True** (R01–R16 deterministic verification)
- `layout_v2`: **True** (Multi-column whitespace projection & reading order)
- `figures_v2`: **True** (Vector extraction & crop refinement)
- `clean_v2`: **True** (Illumination, median watermark & furniture scrubbing)
- `lang_v2`: **True** (KaTeX math, chemistry & Devanagari Unicode maps)
- `answers`: **True** (Answer key, marking scheme & solution binding)
- `s7_repair`: **True** (T0–T4 escalation ladder & JSON patch applier)
- `bank`: **True** (SimHash-64 & number signature 0-token reuse)
- `autoprofile`: **True** (Consensus fingerprinting & automated scaffolding)
- `lessons`: **True** (Autonomous lesson recording & BM25 retrieval)
- `template_v2`: **True** (Jinja2 macros, option grids, offline CSP)
- `exporters`: **True** (Markdown, JSONL, QTI exporters)

---

## 3. Release Sign-Off
All phase gates (0 to 17) passed with 0 regressions. Ready for production deployment.
