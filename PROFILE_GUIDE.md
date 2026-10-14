# ExamForge Declarative Exam Profile Guide

Exam profiles allow ExamForge to adapt to any examination format, language layout, and typography without modifying core pipeline code.

---

## 1. Anatomy of an Exam Profile

Profiles are YAML documents validated against the `ExamProfile` Pydantic model (`src/examforge/profiles/schema.py`).

```yaml
id: neet_ug
name: NEET-UG (National Eligibility cum Entrance Test)
profile_version: 1
engine_min_version: 2.0.0
maturity: verified                   # experimental | draft | verified | retired
extends: [generic_bilingual]

languages:
  - {code: en, script: Latn, direction: ltr}
  - {code: hi, script: Deva, direction: ltr}

language_layout: parallel_columns    # parallel_columns | interleaved | separate_sections | monolingual

layout:
  columns: 2
  spans_allowed: true
  reading_order: parallel            # parallel | columns_ltr | columns_rtl | xy_cut

numbering:
  levels:
    - pattern: '^\s*(\d{1,3})[.)]\s+'
      resets_per_section: true

options:
  schemes:
    - ['(1)', '(2)', '(3)', '(4)']
    - ['(A)', '(B)', '(C)', '(D)']
  count:
    min: 4
    max: 4
  layout_preference:
    - opt-col-1
    - opt-grid-2
    - opt-grid-4

marking:
  patterns:
    - '\+4.*-1'
  default:
    positive: 4.0
    negative: -1.0

furniture_branding:
  footers:
    - 'SPACE FOR ROUGH WORK'
  branding:
    - 'ALLEN'
    - 'RESONANCE'
    - 'FIITJEE'

output:
  template: exam_v2
  layout_mode: bilingual_parallel
  include_answers: false
  exporters: [html, json, markdown, jsonl, qti]

compute: standard
```

---

## 2. Profile Lifecycle: From Scaffold to Verified

1. **Auto-Scaffold**:
   When processing an unseen paper with `--profile auto`, ExamForge infers layout, column geometry, and question numbering, generating a draft profile under `profiles/learned/<id>.yaml` with `maturity: experimental`.
2. **Review & Adjust**:
   Inspect the inferred YAML and preview the layout:
   ```bash
   examforge profile show <profile_id>
   ```
3. **Validate**:
   Run schema and semantic verification:
   ```bash
   examforge profile validate <profile_path>
   ```
4. **Promote**:
   Once validated against ground truth with 100% accuracy, set `maturity: verified` and move to `src/examforge/profiles/builtins/`.
