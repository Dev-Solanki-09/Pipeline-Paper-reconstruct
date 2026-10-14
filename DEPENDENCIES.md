# ExamForge v2 — Dependency Registry

> Per Operating Rule 15: Prefer stdlib and existing dependencies. Any new dependency requires an entry here with version pin, justification, license, and size.

| Package | Version | Required/Optional | License | Justification | Added In |
|---|---|---|---|---|---|
| `click` | >=8.1 | Required | BSD-3-Clause | CLI interface framework | v1 Baseline |
| `pydantic` | >=2.5 | Required | MIT | IR schema data validation & serialization | v1 Baseline |
| `pydantic-settings`| >=2.1 | Required | MIT | Layered settings & environment configuration | v1 Baseline |
| `pyyaml` | >=6.0 | Required | MIT | Declarative YAML specification & profiles | v1 Baseline |
| `pymupdf` (fitz) | >=1.24 | Required | AGPL / Commercial | Digital PDF parsing, rendering & vector drawings | v1 Baseline |
| `pillow` | >=10.0 | Required | HPND | Image processing & cropping | v1 Baseline |
| `numpy` | >=1.26 | Required | BSD-3-Clause | Blur computation & per-pixel median processing | v1 Baseline |
| `jinja2` | >=3.1 | Required | BSD-3-Clause | HTML exam template rendering | v1 Baseline |
| `pytest` | >=8.0 | Dev | MIT | Unit, property, and integration test suite | v1 Baseline |
| `pytest-cov` | >=4.1 | Dev | MIT | Test coverage reporting | v1 Baseline |
| `ruff` | >=0.4 | Dev | MIT | Fast linter and formatter | v1 Baseline |
| `playwright` | >=1.40 | Optional (browser) | Apache-2.0 | Visual render round-trip validation | v1 Baseline |
| `paddleocr` | >=2.7 | Optional (ocr) | Apache-2.0 | Fallback vision model for scanned pages | v1 Baseline |
