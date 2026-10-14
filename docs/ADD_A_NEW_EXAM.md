# Adding a New Exam / Language to ExamForge

This guide details how to add support for a new examination format, regional board, or promote a scaffolded language plugin to ship quality.

---

## 1. Language Plugin Architecture

ExamForge supports multi-lingual and multi-script exam papers via the `ScriptPlugin` protocol in `src/examforge/lang/registry.py`.

Standard ship-quality plugins:
- `en` (English / Latin)
- `hi` (Hindi / Devanagari)

Scaffolded plugins:
- `bn` (Bengali), `ta` (Tamil), `te` (Telugu), `kn` (Kannada), `ml` (Malayalam)
- `gu` (Gujarati), `pa` (Punjabi), `or` (Odia), `mr` (Marathi)
- `ur` (Urdu - RTL), `ar` (Arabic - RTL)
- `zh` / `ja` / `ko` (CJK)

---

## 2. Promoting a Scaffolded Plugin to Ship Quality

To promote a scaffolded plugin (`is_ship_quality = True`):

1. **Create a Dedicated Plugin File:**
   Move the language from `src/examforge/lang/plugins/scaffolded.py` to its own file:
   `src/examforge/lang/plugins/<lang_code>.py`

2. **Implement Required Behaviors:**
   - **NFC & Composition:** Implement script-specific normalization (e.g. Nukta composition, Matra ordering, ZWJ/ZWNJ preservation for conjuncts).
   - **Punctuation Rules:** Handle script-native punctuation (e.g. Dari, Danda, inverted question marks, RTL commas).
   - **Digit Mapping:** Ensure full bidirectional mapping for native numerals.
   - **Bilingual & Mixed Token Rules:** Define boundary detection between Latin formulas/units and the native script.
   - **Legacy Font Maps (if applicable):** Provide mapping tables under `data/fontmaps/<lang_code>_font.json` if common state board papers use legacy 8-bit fonts.

3. **Set `is_ship_quality = True`:**
   Remove the scaffolded status so `NotShipQualityWarning` is no longer emitted.

4. **Add Comprehensive Tests:**
   In `tests/test_lang_plugins.py`, add:
   - NFC normalization idempotence: `normalize(normalize(x)) == normalize(x)`
   - Script-specific conjunct & ligature tests.
   - Punctuation round-trip cases.
   - Mixed prose and formula preservation tests.

5. **Register in Profile:**
   Add the language code to the exam profile YAML under `languages:`.

---

## 3. Adding a New Exam Profile

1. Create `src/examforge/profiles/registry/<exam_id>.yaml`.
2. Define `sections`, `languages`, `question_numbering`, `options`, `figure_cues`, and `answer_key_styles`.
3. Validate using `tests/test_profiles.py`.
4. Ensure zero hardcoded literals in `src/examforge/stages/` by running `tests/test_no_hardcoding.py`.
