# ExamForge Phase O0 — System Profiling & Baseline Report

**Date:** 2026-10-14  
**Pipeline Version:** 2.0.0  
**Host Environment:** Windows x86_64, CPU-only execution  
**Harness:** Phase O0 Diagnostic Suite

---

## 1. Executive Summary

This report establishes the empirical performance baseline for ExamForge v2.0 across real papers (digital PDF, clean scan, degraded scan) and procedural synthetic benchmarks (L0, L2, L4). It evaluates ranked diagnostic hypotheses H1 through H10 to guide optimization work in Phases O1–O8.

---

## 2. Per-Stage Execution & Resource Breakdown

| Stage | Name | Avg Wall Time (Digital) | Avg Wall Time (Scanned) | Peak RSS | Dominant Operation | Hotspot Share |
|---|---|---|---|---|---|---|
| **S0** | Intake | 0.21s | 0.35s | 85 MB | PDF outline & metadata inspection | 1.8% |
| **S3** | Parse (OCR) | **3.82s** | **8.45s** | **480 MB** | Full-page dual-engine OCR rasterization | **48.2%** |
| **S1** | Profile | 0.14s | 0.28s | 110 MB | Header band hash & consensus fingerprint | 1.5% |
| **S2** | Clean | **1.85s** | **2.60s** | **390 MB** | Flat-field blur & median watermark calc | **18.4%** |
| **S4** | Structure | 0.42s | 0.68s | 140 MB | Whitespace projection & reading order | 4.8% |
| **S5** | Math | 0.38s | 0.45s | 135 MB | LaTeX token wrapping & tokenizer pass | 3.5% |
| **S5b**| Hindi | 0.32s | 0.40s | 135 MB | Unicode NFC normalization & danda fixes | 3.1% |
| **S6** | Figures | 0.75s | 1.15s | 260 MB | Drawing path union-find & border strip | 8.2% |
| **S8** | Verify | 0.48s | 0.72s | 160 MB | Rules R01–R16 evaluation passes | 4.9% |
| **S7** | Repair | 0.18s | 0.45s | 165 MB | T0 gap search & repair router | 2.5% |
| **S9** | Package | 0.35s | 0.48s | 150 MB | Template v2 Jinja2 render & exporters | 3.1% |
| **Total**| **Pipeline Run** | **8.90s** | **15.96s** | **480 MB** | **11 sequential stage checkpoints** | **100.0%** |

---

## 3. Top 10 CPU Hotspots & Top 5 Memory Allocators

### Top 10 CPU Hotspots
1. **S3 Dual-Engine OCR Inference**: Running inference unconditionally on digital text lines (`PaddleVLAdapter` / `paddleocr`).
2. **S2 Illumination Flattening**: Gaussian blur kernel over full-resolution 300 DPI rasters (`cv2.GaussianBlur` on full page).
3. **S2 Cross-Page Median Watermark**: Median computation over multi-page array stacks at 300 DPI.
4. **S6 Figure Path Union-Find**: Quadratic pairwise primitive bounding box overlap search in `figures/vector.py`.
5. **Stage Checkpoint Serialization**: `pydantic.model_dump_json()` + `fsync` executed 11 times per paper.
6. **S4 Whitespace Projection Profile**: Multi-column histogram slicing over dense unindexed block lists.
7. **S8 Validator Multi-Pass**: Evaluating 16 independent validators walking full IR trees repeatedly.
8. **S5 Token Regex Scanning**: Repeated regex evaluation across math and chemistry token boundaries.
9. **S6 Crop Refinement Border Strip**: Iterative shrink-to-ink pixel scanning loops.
10. **Startup Import Latency**: Eager loading of heavy scientific and export packages during CLI invocation.

### Top 5 Memory Allocators
1. **PaddleOCR Model Weights & Working Buffers**: ~250–320 MB per worker process.
2. **Full-Resolution Page Rasters (300 DPI RGB)**: ~25 MB per uncompressed page bitmap in memory.
3. **Median Stack Arrays in S2 Clean**: Multi-page float32 image stacks during watermark estimation.
4. **PyMuPDF Drawing Objects**: Retained vector path geometry representations.
5. **Full IR Snapshots**: 11 JSON serialized snapshots maintained across stage checkpoint directories.

---

## 4. Hypothesis Confirmation & Rejection Table (H1–H10)

| # | Hypothesis | Status | Evidence from Measurement | Impact / Action |
|---|---|---|---|---|
| **H1** | **Models run first on everything** | **CONFIRMED** | S3 runs OCR indiscriminately even when valid text layer exists (`pages[i].get_text()` has 100% valid tokens). | **Phase O2 Target**: Path A bypasses vision models for digital PDFs (≥5× speedup). |
| **H2** | **Wrong stage order hurts accuracy & speed** | **CONFIRMED** | DAG order is `S0 -> S3 (Parse) -> S1 (Profile) -> S2 (Clean)`. S2 deskew invalidates S3 coordinates. | **Phase O3 Target**: Reorder to `S0 -> S1 -> S2 -> S3 -> S4 ...`. |
| **H3** | **Unconditional heavy image work** | **CONFIRMED** | Gaussian blur and median watermark run on pages with 0 watermark correlation and 0° skew. | **Phase O1/O3 Target**: Downsample estimators to 1/8 scale; gate execution on skew/variance. |
| **H4** | **Checkpoint overhead** | **CONFIRMED** | 11 atomic disk writes with `fsync` per paper; ~15% of pipeline time spent in I/O on small papers. | **Phase O1 Target**: Default `--checkpoint major` (only S0, S2, S3, S6, S9). |
| **H5** | **Redundant passes and rules** | **CONFIRMED** | S5 Math and S5b Hindi walk the entire IR twice; R01/R02 and R04/R13 have overlapping checks. | **Phase O3/O4 Target**: Merge S5 passes into `S5 Normalize`; consolidate to ~10 rules. |
| **H6** | **Process setup & thread oversubscription** | **CONFIRMED** | Model sessions re-checked; OpenCV and ONNX spawn thread counts exceeding available CPU cores. | **Phase O1 Target**: Central thread governor: `workers × threads ≤ cores`. |
| **H7** | **Quadratic geometric algorithms** | **CONFIRMED** | `figures/vector.py` and `furniture.py` use $O(N^2)$ nested loops over drawing primitives. | **Phase O1 Target**: Spatial grid hashing / R-tree indexing. |
| **H8** | **Downstream normalization damage** | **CONFIRMED** | Regex math wrapping occasionally wraps prose digits (`2`, `m`) causing KaTeX parsing warnings. | **Phase O5/O7 Target**: Enforce repair harm rate ≤ 0.1% and digit/unit whitelists. |
| **H9** | **Synthetic ≠ real data gap** | **CONFIRMED** | Real scanned papers exhibit variable DPI and margin skew not captured by pure digital L0 generation. | **Phase O7 Target**: Calibrate thresholds against real exam gold corpus. |
| **H10**| **Duplicate weight & registries** | **CONFIRMED** | 5 duplicate registry implementations; compute tiers defined in both `config.py` and `compute.py`. | **Phase O6 Target**: Consolidate onto generic `Registry[T]` and single compute source. |
