# Migration Guide: ExamForge v1.x to v2.0

ExamForge v2.0 introduces Intermediate Representation (IR) v2, universal exam profiles, and multi-format exporters while preserving 100% backward compatibility with v1 `document.json` files and pipeline commands.

---

## 1. Key Architectural Changes

1. **Intermediate Representation**:
   - v1 stored raw block lists (`blocks: list[Block]`) and language text strings (`stem_text_en`, `stem_text_hi`).
   - v2 introduces structured `ContentNode` discriminated unions (`TextNode`, `MathNode`, `TableNode`, `FigureNode`, `StatementsNode`, etc.) supporting arbitrary question shapes and N-languages.
   - Compatibility accessors (`question.stem_text_en`, `question.text_str_en`) remain available and computed dynamically.

2. **Migrating Existing v1 Documents**:
   Use `migrate_v1_to_v2`:
   ```python
   from examforge.ir.migration import migrate_v1_to_v2, load_document

   # Automatically detects v1 and migrates to v2
   doc_v2 = load_document("runs/legacy_run/document.json")
   assert doc_v2.schema_version == 2
   ```

3. **CLI Command Modernization**:
   - Old: `examforge execute --exam paper.pdf --profile neet_ug`
   - New: `examforge execute paper.pdf` (defaults to auto-profiling and v2 flags)

4. **Output Formats**:
   - v1 emitted only `output.html`.
   - v2 automatically exports `output.html`, `document.json`, `output.md`, `questions.jsonl`, and `qti.xml`.
