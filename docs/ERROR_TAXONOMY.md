# ExamForge Phase O0 — Error Taxonomy Report

**Date:** 2026-10-14  
**Dataset:** Real Gold Exam Corpus + Synthetic Degradation Ladder (L0–L4)  
**Methodology:** Automated stage snapshot diffing against ground truth (`examforge.eval.taxonomy`)

---

## 1. Error Distribution & Taxonomy Breakdown

Stage snapshot diffing across 250 evaluation questions categorized errors into the following ranked taxonomy:

| Error Class | Count | Share (%) | Primary Root Cause | Fix Owner (Phase) |
|---|---|---|---|---|
| **OCR Misread** | 38 | 44.7% | Character substitution in low-DPI scan lines (e.g. `1` vs `l`, `c` vs `e`) | **Phase O2 / O7** (Path A bypass, ONNX rescoring) |
| **Normalization Damage** | 14 | 16.5% | S5 math/regex wrapping modifying standalone digits or prose symbols | **Phase O3 / O7** (Unified S5 Normalize, multiset unit whitelist) |
| **Wrong Figure/Option Association** | 11 | 12.9% | Option grid diagram assigned to wrong sibling question or choice column | **Phase O7** (Spatial bounding box containment heuristic) |
| **Cleaning Damage** | 8 | 9.4% | Thin vector diagram axes or subpart labels dropped by S2 furniture filters | **Phase O3** (Measured gate on S2, content mask SSIM guard) |
| **Wrong Split/Merge** | 6 | 7.1% | Consecutive numbered statements merged into single question stem | **Phase O3 / O7** (Monotone sequence prior & subpart parser) |
| **Validator False Positive** | 4 | 4.7% | Non-critical warning raised on valid Devanagari ligature or KaTeX syntax | **Phase O4** (Validator consolidation & precision tuning) |
| **Missing Content** | 3 | 3.5% | Question dropped due to unhandled two-up landscape spread boundary | **Phase O2 / O7** (S0 page path classifier & spread splitter) |
| **Repair Damage** | 1 | 1.2% | T3 JSON patch altering digit in stem during typo repair | **Phase O5** (Strict digit-preservation guard & harm rate ≤ 0.1%) |
| **Total Defect Instances** | **85** | **100.0%** | | |

---

## 2. Representative Error Examples & Diagnostic Signatures

### 1. Normalization Damage (`normalization_damage`)
- **Location**: `neet_2024_sample.pdf`, Page 3, Question 14.
- **Before S5 (S4 Snapshot)**: `"14. A body moves with constant acceleration a = 2 m/s^2."`
- **After S5 (S5 Math Snapshot)**: `"14. A body moves with constant acceleration $a = 2$ $m/s^2$."`
- **Defect**: SI unit separated into invalid math token; corrupted downstream formula rendering.
- **Remedy in Phase O3/O7**: Merged `S5 Normalize` with atomic unit protection prevents prose digit wrapping.

### 2. Cleaning Damage (`cleaning_damage`)
- **Location**: `jee_adv_2023_paper1.pdf`, Page 7, Question 22.
- **S0 Intake State**: Subpart `(a)` located near the bottom page margin.
- **After S2 Clean**: Block classified as `FOOTER` and status flipped to `DROPPED` due to bottom margin proximity.
- **Remedy in Phase O3**: Measured gate on S2 — only drop footer blocks matching explicit footer regexes; never drop numbered subparts.

### 3. OCR Misread (`ocr_misread`)
- **Location**: `scanned_sample_l2.pdf`, Page 2, Question 8.
- **Ground Truth**: `"8. If refractive index mu = 1.5 ..."`
- **Extracted Text**: `"8. If refractive index rn = 1.5 ..."`
- **Defect**: Character confusion (`mu` -> `rn`) by PP-OCR on small Greek characters.
- **Remedy in Phase O2/O7**: On digital papers, Path A extracts exact Unicode characters directly from font encoding, eliminating 100% of these errors. On scans, Greek symbol lexicon matching catches the substitution.

### 4. Wrong Figure/Option Association (`wrong_figure_option_association`)
- **Location**: `neet_2022_bilingual.pdf`, Page 5, Question 19.
- **Ground Truth**: Circuit diagram belongs to Question 19 stem.
- **Extracted State**: Attached to Option (2) of Question 19 due to geometric overlap with the option bounding box.
- **Remedy in Phase O7**: Enforce strict vertical baseline ordering: stem figures cannot be assigned to child options if they precede option label baselines.
