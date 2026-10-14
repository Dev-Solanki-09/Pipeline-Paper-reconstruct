# ExamForge Token Accounting & Budget Governor

ExamForge v2 achieves a **>60% token reduction** per question compared to naive whole-page vision-language model (VLM) architectures.

---

## 1. The Token Budget Governor (`examforge/llm/budget.py`)

Every LLM request routes through the `TokenBudgetGovernor`:
- **Per-Run Budget**: Hard cap on total tokens spent in a single paper execution (default: 50,000 tokens).
- **Per-Question Budget**: Maximum tokens allowed for any individual question (default: 1,500 tokens).
- **Per-Stage Budget**: Allocated spend per stage (e.g. S1 autoprofile: 2,000 tokens; S7 repair: 30,000 tokens).
- **Graceful Downgrade**: If budget is exhausted, the pipeline degrades to T4 human review (`EXIT_NEEDS_REVIEW`, 20) rather than failing or blowing costs.

---

## 2. The Content-Addressed Prompt Cache (`examforge/llm/cache.py`)

- Prompts and system instructions are hashed with SHA-256.
- Responses are stored in a persistent SQLite/disk cache.
- Rerunning an identical paper or identical question repair spends **0 tokens**.

---

## 3. Escalation Ladder Economics

| Tier | Method | Expected Token Spend | Resolution Share |
|---|---|---|---|
| **T0** | Deterministic gap re-search, STEM lexicon typo lookup | **0 tokens** | ~65% of issues |
| **T1** | Local crop re-OCR with alternative thresholding | **0 tokens** | ~15% of issues |
| **T2** | Small model candidate chooser from contact sheet | **~1-5 tokens** | ~10% of issues |
| **T3** | Strong model JSON patch on isolated question stem | **~150 tokens** | ~8% of issues |
| **T4** | Escalate to `review.html` (exit code 20) | **0 tokens** | ~2% of issues |

---

## 4. Reading the Telemetry Ledger

At the end of each run, `manifest.json` and `ledger/ledger.jsonl` record:
- `tokens_prompt`: Total prompt tokens sent.
- `tokens_completion`: Total completion tokens received.
- `tokens_saved_cache`: Tokens saved via SHA-256 cache hits.
- `tokens_saved_bank`: Questions resolved 100% via verified bank SimHash-64 reuse.
- `llm_touched_ratio`: Percentage of questions requiring any model inference (target: <= 15%).
