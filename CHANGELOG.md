# Changelog

All notable changes to ExamForge are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] — 2026-10-14

### Added
- **Universal IR v2**: Discriminated union `ContentNode` system supporting text, math, figures, tables, statements, match columns, code, and raw crops across arbitrary languages.
- **Declarative Exam Profiles**: Extensible YAML exam profile system with deep inheritance, capability negotiation, and compute tiers (`lite`, `standard`, `gpu`).
- **Synthetic Ground Truth Generator (L0–L4)**: Deterministic procedural exam generator, diagram synthesizer, degradation ladder, and universal benchmark covering matrix.
- **Deterministic Verifiers (R01–R16)**: Rule engine covering language consistency, text layer agreement, STEM lexicons, KaTeX syntax, sequence monotonicity, structure consistency, and answer binding.
- **Universal Multi-Column Layout**: Whitespace projection column segmentation, multi-strategy reading order, subpart nesting, and ReDoS guards.
- **Vector-First Figure Pipeline**: PyMuPDF drawing union-find clustering, grow-until-clean crop refinement, and table structure recovery.
- **Restoration & Cleaning Engine**: Projection variance deskew, flat-field division shadow removal, median watermark scrubbing, and script-aware furniture filtering.
- **Domain Lexicons & Scripts**: Bilingual token wrapping, KaTeX/mhchem math and chemistry formatting, and KrutiDev/Chanakya font decoding.
- **Answer Key & Solutions Binding**: Automated parsing of answer tables, marking scheme extraction, and solution attachment.
- **Escalation Ladder & S7 Repair**: T0–T4 escalation hierarchy with Platt-scaled confidence calibration, FakeLLM offline fallback, and human review deck.
- **Verified Question Bank**: SimHash-64 content matching with strict numeral and unit signatures enabling 0-token question reuse.
- **Auto-Profiling & Scaffolding**: Document consensus fingerprinting, SQLite cache, and automated draft profile scaffolding.
- **Template v2 & Exporters**: Single-file offline HTML template, greedy option packing (`opt-grid-2`, `opt-grid-4`), and Markdown, JSONL, and QTI exporters.
- **Self-Improving Loop**: Append-only lesson recording, BM25 retrieval, and automated rule promotion.
- **Orchestrator Hardening**: Formal Stage DAG, atomic I/O with fsync, cross-platform run locks, 50MP bomb protection, and plugin isolation.

### Changed
- All 12 v2 feature flags enabled by default.
- CLI command `examforge execute <paper>` now defaults to `--profile auto` and accepts positional paper paths.
- Exit code 20 consistently generates `review.html` for human review.
