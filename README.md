# ExamForge

Turn scanned or digital Indian exam papers (NEET-UG, JEE, UPSC) into clean, printable, bilingual (English + Hindi) HTML — with correct text, accurate formulas, and clean diagrams.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run on an exam PDF
examforge execute --exam path/to/exam.pdf --mode fast

# Resume a failed run
examforge resume --run-id <run_id>

# Inspect a completed run
examforge inspect --run-id <run_id>
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | All gates pass |
| 10   | Pass with warnings |
| 20   | Needs human review |
| 30   | Failed |

## Project Structure

```
src/examforge/
  cli.py              # Click CLI entrypoint
  config.py           # Layered configuration (YAML + env + CLI)
  spec.py             # Frozen specification rules
  ir/schema.py        # Intermediate representation (Pydantic models)
  orchestrator/       # Pipeline runner, manifest, run directories
  stages/             # S0 Intake … S9 Package
  validators/         # One module per spec rule
  templates/          # Jinja2 HTML templates
```

See [ExamForge Architecture and Build Plan.md](ExamForge%20Architecture%20and%20Build%20Plan.md) for the full design.
