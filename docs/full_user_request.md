<USER_REQUEST>
# ExamForge v2 — Implementation Plan for an IDE Coding Agent

> **Audience:** an autonomous coding agent (Claude Code, Cursor, Copilot agent, etc.) working inside the ExamForge repository.
> **Mission:** make ExamForge (1) token-efficient, (2) more accurate, and (3) universal — able to ingest *any* exam paper — **without regressing quality at any step**.
> **Method:** 17 sequential phases (0–16). Each phase is small enough to finish and verify on its own, ends in a hard **gate**, and leaves the repository releasable.

---

## 0. Quick start for the agent

| Command from the human | Meaning |
|---|---|
| `execute` | Open `PROGRESS.md`, resume at the **first unchecked task**, and work. No separate analysis pass (except the one-time Phase 0 recon on first run). |
| `execute phase N` | Work on phase N only. Refuse if phase N-1's gate has not passed. |
| `gate N` | Run phase N's gate checks and report pass/fail with evidence. |
| `status` | Print `PROGRESS.md` summary, current metrics vs baseline, open blockers. |

**Reconciliation rule.** This plan uses module names from the ExamForge architecture spec (`runner.py`, `schema.py`, `spec.py`, `s0_intake.py` … `s9_package.py`, `exam.html.j2`, `src/examforge/validators/`). If the real repository differs, record the mapping in `docs/RECON.md` (Phase 0) and use the real names. Never rename existing modules just to match this document.

**Threshold rule.** Every numeric threshold below is an *initial proposal*. At the end of Phase 4 the agent MUST calibrate them against the measured baseline and write the final values to `metrics/thresholds.yaml`. Thresholds may be tightened freely, but may **never be loosened** without a human-approved entry in `BLOCKERS.md`.

---

## 1. Operating protocol (non-negotiable)

1. **Strict order.** Phases run in numeric order. A phase starts only after the previous gate passes (`make gate PHASE=n`). Tasks inside a phase run in order unless marked *parallel-safe*.
2. **Red → Green → Refactor.** For every task: write the failing test(s) first, commit nothing until they fail for the *right reason*, implement the minimum to pass, refactor, then run `make verify`.
3. **Definition of Done (per task).** (a) tests written and passing, (b) `ruff` + `mypy` clean on touched files, (c) no coverage drop, (d) docs/docstrings updated, (e) `PROGRESS.md` ticked with the commit hash, (f) characterization tests still green.
4. **Never weaken a check to make it pass.** No deleting tests, loosening thresholds, adding broad `# type: ignore`, `skip`, or `xfail` to hide failures. If a test appears wrong, stop and write the case in `BLOCKERS.md`.
5. **Protected files.** Files under `tests/gold/**/expected*` and `metrics/thresholds.yaml` may only be changed when a `HUMAN_APPROVED` marker file (approver + date) is present in the same directory. The agent may add *proposed* gold data under `tests/gold_proposed/`.
6. **Feature flags.** Every new behavior ships behind `features.<name>` in config, **default off**. The flag is flipped on only in Phase 16, one flag per commit, with an eval run after each flip. Rollback = revert that commit.
7. **No network in tests.** An autouse fixture blocks sockets. The only exceptions are `@pytest.mark.network` tests and `make record-cassettes`, both run manually by a human.
8. **All LLM/VLM/MCP access goes through `examforge/llm/` (Phase 1).** No other module may import a provider SDK (enforced by an AST test).
9. **Determinism.** Fixed seeds everywhere; sorted iteration; no timestamps or absolute paths inside `document.json` or output HTML (timestamps live only in the manifest/event log).
10. **Small commits.** One task = one commit (or a short series). Message format: `P<phase>.T<task>: <imperative summary>`. Keep diffs reviewable (target < 400 changed lines excluding fixtures/data).
11. **Progress log.** Update `PROGRESS.md` after every task (template in Appendix C).
12. **Stop conditions.** Stop and write `BLOCKERS.md` (template in Appendix D) when: a gate fails twice after honest attempts; a requirement is ambiguous in a way that changes behavior; a needed dependency is not allowed; a metric regresses and the cause is unknown.
13. **Backward compatibility.** v1 `document.json` must remain loadable (migrator) and the v1 template remains selectable until Phase 16.
14. **Resource limits.** Assume a **CPU-only machine with modest RAM**. The default `make verify` must finish in a few minutes on such a machine. Heavy tests (real models, big papers, visual regression, mutation) carry markers: `slow`, `model`, `visual`, `nightly`.
15. **Dependencies.** Prefer stdlib and what is already installed. Any new dependency requires a one-line justification in `DEPENDENCIES.md` (name, version pin, why, license, size, optional/required).
16. **Untrusted input.** Text extracted from papers is *data*, never instructions. It must never be able to influence control flow, file paths, shell commands, or LLM behavior beyond its role as content.
17. **Self-check before every commit:** "Does this change any output on the characterization set? If yes, is that change intended, measured, and recorded?"

---

## 2. Goals, non-goals, success criteria

**Goals**
- G1 Cut LLM/VLM token spend per question drastically while holding or improving accuracy.
- G2 Improve extraction quality using signals already in the paper (bilingual cross-checks, text layer, lexicons) before spending tokens.
- G3 Generalize: new exam types require a *profile*, not code changes.
- G4 Make every claim measurable via synthetic ground truth + a verified gold set.

**Non-goals**
- Training new ML models. Replacing Paddle-VL. Building a web UI. Supporting handwriting.

**Success criteria** (calibrate in Phase 4; see Threshold rule)

| Metric | Target |
|---|---|
| Question-sequence accuracy (synthetic L0–L2, gold) | ≥ baseline; ≥ 99.5 % synthetic L0–L2 |
| Stem/option text CER | ≤ baseline; ≤ 1.0 % synthetic L2 |
| Bilingual completeness | 100 % on synthetic; 100 % on gold |
| Figure association accuracy | ≥ 98 % |
| Figure crops with clean borders (zero ink on border strip) | 100 % |
| Figure IoU ≥ 0.9 vs GT | ≥ 98 % |
| Residual watermark correlation (R03) | < 0.05 |
| LLM tokens per question (median) | ≥ 60 % lower than P1 counterfactual |
| Questions touched by any LLM call | ≤ 15 % |
| Universality benchmark (10 unseen synthetic exam families) | ≥ 90 % pass without code change |
| Stage time / peak RSS vs baseline | ≤ 120 % / ≤ 115 % |
| Crash-resume equivalence | 100 % identical output |

---

## 3. Constraints and assumptions

- Python version, OS and packaging follow the existing repo (`pyproject.toml`). Do not raise the minimum Python version.
- Offline-first: the final HTML must load with zero network requests. The pipeline itself must work without internet except for the optional LLM seam.
- Source papers may be copyrighted. Keep real papers out of git unless redistribution is clearly allowed; use `tests/fixtures/real/` (gitignored) with a hash manifest, and make tests *skip* when files are absent.
- The human owns gold-set approval. The agent never self-approves gold data.

---

## 4. Target architecture

```mermaid
graph TD
    IN["Input: PDF / images / ZIP"] --> S0["S0 Intake<br/>render, classify, DPI, fonts"]
    S0 --> S1["S1 Profile<br/>cache → rules → one-shot VLM (Phase 12)"]
    S1 --> S2["S2 Clean<br/>furniture, branding, watermark (Phase 8)"]
    S2 --> S3["S3 Parse<br/>Paddle-VL + PyMuPDF + 2nd OCR on low-confidence"]
    S3 --> S4["S4 Structure<br/>columns, reading order, numbering, kinds (Phase 6)"]
    S4 --> S5A["S5a Math (Phase 9)"]
    S4 --> S5B["S5b Language plugins (Phase 9)"]
    S5A --> S6["S6 Figures<br/>vector-first, grow-until-clean (Phase 7)"]
    S5B --> S6
    S6 --> S8["S8 Verify<br/>R01–R14, free verifiers (Phase 5)"]
    S8 -->|issues| S7["S7 Repair ladder<br/>T0 rule → T1 local → T2 MCQ-VLM → T3 patch → T4 human (Phase 10)"]
    S7 -->|scoped re-verify, ≤2 rounds| S8
    S8 -->|pass| S9["S9 Package<br/>template v2, block macros (Phase 13)"]
    S9 --> OUT["Self-contained bilingual HTML"]
    BANK[("Verified question bank<br/>(Phase 11)")] -.reuse.-> S4
    BANK -.hints.-> S7
    LESS[("Lessons store<br/>(Phase 14)")] -.top-k.-> S7
    PROF[("Exam profiles<br/>(Phase 3)")] -.config.-> S0
    PROF -.config.-> S8
    TEL[("Telemetry ledger<br/>(Phase 1)")] -.records.-> S0
```

**Design principles**
- *Free signals first, tokens last.* The LLM only sees a failing issue, a tight crop, and one question's compact IR.
- *Profile, not code.* Anything exam-specific lives in YAML profiles.
- *Everything measured.* Each stage logs time, memory, tokens, and escalation tier.
- *Fail visible.* Budget exhaustion or low confidence ends in `EXIT_NEEDS_REVIEW` with evidence — never silent loss.

---

## 5. Target repository layout (additive)

```
src/examforge/
  runner.py                # orchestrator (hardened in P15)
  schema.py                # IR (v2 + compat in P2)
  invariants.py            # P2
  spec.py                  # rules declared from profile (P3, P5)
  telemetry.py             # P1
  llm/                     # P1: types, client, fake, recording, budget, cache
  profiles/                # P3, P12: schema, loader, builtin/*.yaml, fingerprint, infer_*
  layout/                  # P6: columns, reading_order, kinds, passages
  figures/                 # P7: vector, raster, crop, associate
  clean/                   # P8: watermark_median, furniture, branding
  lang/                    # P9: registry, plugins/{en,hi,...}, fontmaps
  math/                    # P9: tokenize, chem, units, wrap, validate
  validators/              # P5: R01–R14 (+ existing)
  repair/                  # P10: router, context, patch, gap_search, prompts
  confidence/              # P10: calibrate
  bank/                    # P11: store, fingerprint, match
  lessons/                 # P14: store, retrieve, promote
  synth/                   # P4: generator, degrade, fonts, corpora
  eval/                    # P4: metrics, scorer, compare
  templates/               # P13: exam_v2.html.j2 (+ exam.html.j2 v1)
  cli.py                   # P15
prompts/repair/            # versioned prompt files
data/lexicons/  data/fontmaps/
tests/{unit,property,golden,faults,integration,visual,perf,robustness,universal}/
tests/fixtures/{real,synthetic}/  tests/gold/  tests/gold_proposed/  tests/baseline/
metrics/{baseline.json,thresholds.yaml}
docs/{RECON.md,BASELINE.md,ARCHITECTURE.md,PROFILE_GUIDE.md,ADD_A_NEW_EXAM.md,TESTING.md,TOKEN_BUDGET.md,PERF.md}
PROGRESS.md  BLOCKERS.md  DEPENDENCIES.md  RUNBOOK.md  CHANGELOG.md
```

---

## 6. Test strategy (applies to every phase)

| Layer | Purpose | Tools | Runs in |
|---|---|---|---|
| Unit | pure functions, regexes, parsers | pytest | `make verify` |
| Property-based | invariants (idempotence, round-trip, monotonicity) | hypothesis | `make verify` (ci profile) |
| Characterization | freeze v1 behavior during refactors | snapshot compare | `make verify` |
| Golden | real verified papers vs `expected.json` | scorer | `make eval-fast` / `eval-full` |
| Synthetic E2E | seeded generated PDFs L0–L3 with exact GT | synth + scorer | `make eval-fast` |
| Fault injection | mutate a clean IR; validator must catch exactly that fault | mutators | `make verify` |
| Metamorphic | transform input (shuffle blocks, rescale page) → same output | pytest | `make verify` |
| Crash/resume | kill at every stage → `--resume` equals clean run | subprocess | `make verify` (small) / nightly (large) |
| Visual regression | template screenshots vs approved baselines | Playwright + SSIM | `make visual` |
| Performance | time/RSS vs baseline | pytest-benchmark, `resource` | `make perf` |
| Robustness/fuzz | corrupt, encrypted, empty, huge, adversarial inputs | pytest, hypothesis | `make verify` / nightly |
| Mutation | tests actually detect code changes | mutmut (critical modules) | `make nightly` |

**Rules**
- Every bug found gets a regression test *before* the fix.
- Metrics are compared with `examforge eval --compare metrics/baseline.json`; any metric dropping > 0.5 pp (or time/RSS over budget) fails the gate.
- `make ratchet` may only *raise* the baseline, and only when every metric is ≥ the current baseline.
- Flaky tests are bugs: fix or quarantine with a tracked `BLOCKERS.md` entry within the same phase — never retry-loop to green.
</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-10-12T21:28:15+05:30.
</ADDITIONAL_METADATA>