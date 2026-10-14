# ExamForge Phase O0 — Redundancy & Dead Weight Audit

**Date:** 2026-10-14  
**Pipeline Version:** 2.0.0  
**Scope:** Repository static analysis, import dependencies, registry duplication, and dead code candidates.

---

## 1. Registry Duplication & Consolidation Candidates

The repository contains **five parallel registry implementations**, all implementing custom dictionary storage with varying interfaces:

| Registry Location | Class Name | Items Managed | Consolidation Plan (Phase O6) |
|---|---|---|---|
| `src/examforge/registry.py` | `Registry[T]` | Generic base registry | **Target Single Source of Truth** |
| `src/examforge/validators/registry.py` | `ValidatorRegistry` | Rule validators (R01–R16) | Migrate to `Registry[Validator]` |
| `src/examforge/lang/registry.py` | `LanguagePluginRegistry` | Script plugins (`en`, `hi`, etc.) | Migrate to `Registry[ScriptPlugin]` |
| `src/examforge/export/registry.py` | `ExporterRegistry` | Exporters (`html`, `json`, `md`, etc.) | Migrate to `Registry[Exporter]` |
| `src/examforge/orchestrator/plugins.py` | `PluginManager` | Dynamic user plugins | Use `Registry[Plugin]` |

**Impact**: Eliminates ~400 lines of boilerplate, aligns registration methods, and allows unified capability lookup.

---

## 2. Duplicate Configuration & Compute Tier Definitions

Compute tiers (`lite`, `standard`, `gpu`) and resource ceilings are declared in two separate places:
1. `src/examforge/config.py`: Contains inline definitions and configuration fields for engines, paths, and flags.
2. `src/examforge/profiles/compute.py`: Contains `ComputeTier`, `ComputeConfig`, and tier presets (`LITE_TIER`, `STANDARD_TIER`, `GPU_TIER`).

**Consolidation Plan (Phase O1/O6)**:
- Consolidate all compute tier definitions into `src/examforge/profiles/compute.py`.
- Let `ExamForgeConfig` reference `ComputeConfig` directly as its single source of truth for worker and thread allocation.

---

## 3. Redundant Pipeline Stages & Passes

1. **S5 Math (`s5_math.py`) and S5 Hindi (`s5_hindi.py`)**:
   - Both stages walk all questions, stems, and options across the entire document.
   - S5 Math extracts math tokens, runs regex canonicalization, and wraps LaTeX.
   - S5 Hindi runs immediately afterward, walking the exact same questions to perform Unicode NFC normalization and danda fixes.
   - **Merge Target (Phase O3)**: Combine into a single-pass `S5 Normalize` that traverses each question once, performing notation canonicalization and script normalization simultaneously.

2. **Overlapping Validators (R01–R16)**:
   - `R01 No Furniture` & `R02 No Branding`: Both iterate through dropped/active blocks scanning regex pattern lists. -> Merge into `furniture_branding`.
   - `R04 Continuous Flow` & `R13 Render Check`: Both check container health and rendering consistency. -> Merge into `packaged_output_check`.
   - `R05 Bilingual Pairing` & `R10 Language Consistency`: Both evaluate bilingual token agreement. -> Merge into `language_consistency`.
   - `R06 Completeness`, `R14 Sequence Gaps` & `R15 Structure Consistency`: Overlapping structure and numbering checks. -> Merge into `structure_integrity`.
   - **Target (Phase O4)**: Consolidate 16 rules into ~10 cost-tiered rules, reducing verification time by >50%.

---

## 4. Lazy-Load Candidates (CLI Startup Latency)

Currently, executing `examforge --help` triggers several top-level imports that slow down CLI responsiveness:

| Module | Why Eagerly Loaded | Lazy Load Solution (Phase O1) |
|---|---|---|
| `examforge.export.qti` (lxml / XML parsers) | Imported in export registry | Import only when `--format qti` or profile asks |
| `examforge.lang.fontmaps` (large mapping dicts) | Top-level import in `lang` package | Lazy-load font dictionary upon first KrutiDev detection |
| `examforge.lang.plugins.scaffolded` (10 script plugins) | Imported at module initialization | Discover dynamically on demand |
| `cv2` (OpenCV) | Imported in cleaning/figures modules | Import within stage execution bodies |

**Target**: Reduce `examforge --help` execution from ~0.8s to < 0.25s.

---

## 5. Dead Code & Legacy Assets

1. **`src/examforge/templates/exam.html.j2` (v1 Template)**:
   - Preserved for characterization rollback during Phase 14–17.
   - With all 12 feature flags default True and `template_v2` verified, v1 template is ready for retirement once approved.
2. **`src/examforge/ir/migrator.py`**:
   - Keep as a lightweight loader for legacy v1 documents, but isolate from the primary v2 processing path.
