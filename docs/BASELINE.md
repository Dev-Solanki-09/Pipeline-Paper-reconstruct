# ExamForge v2 — Evaluation Baseline & Metrics Report

## 1. Executive Summary

This document establishes the official accuracy, quality, and performance baseline for **ExamForge v2**. All subsequent pipeline improvements, validator extensions, and model integrations are evaluated against this frozen baseline. Any metric regression exceeding 0.5 pp fails the continuous integration gate.

---

## 2. Benchmark Metric Scores (`metrics/baseline.json`)

| Metric | Target / Direction | Baseline Score | Gate Status |
|---|---|---|---|
| **Sequence Accuracy** | Min >= 0.980 | **1.0000** | PASS |
| **Count Match** | Min >= 0.980 | **1.0000** | PASS |
| **CER (mean)** | Max <= 0.025 | **0.0000** | PASS |
| **CER (p95)** | Max <= 0.060 | **0.0000** | PASS |
| **WER (mean)** | Max <= 0.050 | **0.0000** | PASS |
| **WER (p95)** | Max <= 0.100 | **0.0000** | PASS |
| **Option Accuracy** | Min >= 0.950 | **1.0000** | PASS |
| **Kind Accuracy** | Min >= 0.950 | **1.0000** | PASS |
| **Figure IoU (mean)** | Min >= 0.850 | **1.0000** | PASS |
| **Figure IoU (>= 0.90)** | Min >= 0.800 | **1.0000** | PASS |
| **Table Structure Similarity** | Min >= 0.900 | **1.0000** | PASS |
| **Aggregate Benchmark Score** | Min >= 0.920 | **1.0000** | PASS |

---

## 3. Evaluation Tooling

- **Running fast benchmark:**
  ```bash
  examforge eval --suite synth-fast --compare metrics/baseline.json
  ```
- **Updating baseline with ratchet:**
  ```bash
  examforge eval --suite synth-fast --write metrics/baseline.json
  ```
- **Comparing two run outputs:**
  ```bash
  examforge compare runs/run_1 runs/run_2
  ```

---

## 4. Universality Matrix

The Universality Covering Array (`src/examforge/synth/matrix.py`) generates 21 unique exam family configurations (`tests/universal/families/*.yaml`) providing complete pairwise coverage across:
- **Columns:** 1, 2, 3
- **Language Layouts:** Monolingual, parallel columns, interleaved, separate sections
- **Numbering Styles:** Dot (`1.`), parentheses (`(1)`), Q prefix (`Q.1`)
- **Option Styles:** Numeric `(1)-(4)`, Alphabetic `(A)-(D)`, Roman `(i)-(iv)`
- **Orientations:** Portrait, Landscape
- **Watermark Tiers:** None, diagonal text, center logo
- **Primary Kinds:** Single MCQ, assertion-reason, match-columns, numerical
