# ExamForge v2.0 Testing Strategy & Quality Gates

ExamForge maintains a zero-regression, offline-deterministic testing methodology.

---

## 1. Safety Harness & Network Isolation

- **Autouse Socket Blocker**:
  `tests/conftest.py` installs an autouse fixture that intercepts and blocks all network socket creation attempts (`pytest-socket`).
  Any unexpected outbound HTTP/TCP request raises a test failure immediately.
- **Offline Mocking & Cassettes**:
  All LLM interactions use `FakeLLMClient` with deterministic responses, or recorded cassettes under `tests/cassettes/`.
- **Reproducibility**:
  Random seeds are explicitly locked (`seed=42`) across all synthetic data generators, degrading ladders, and figure renderers.

---

## 2. Test Markers

| Marker | Purpose | Execution Cadence |
|---|---|---|
| *(default)* | Fast unit and integration tests | Per-task, CI, pre-commit |
| `slow` | Heavy compute tests (PDF rasterization, matrix sweeps) | Scheduled / CI |
| `model` | OCR/VLM weight inference | Local GPU / offline testing |
| `visual` | Playwright screenshot diffing | Regression checks |
| `nightly` | Mutation testing (`mutmut`) and 1000-seed fuzzing | Nightly pipeline |
| `network` | Real network cassette recording | Human maintenance only |

---

## 3. Running Tests

Run the default fast test suite:
```bash
pytest -m "not slow and not model and not visual and not nightly and not network" -q
```

Run specific phase gate verification:
```bash
pytest tests/test_gate17_acceptance.py -q
```
