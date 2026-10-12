"""
ExamForge CLI.

Commands:
    execute  — Run the pipeline on an exam PDF
    resume   — Resume a previously interrupted run
    inspect  — Show manifest and summary for a completed run

Exit codes:
    0   All gates pass
    10  Pass with warnings
    20  Needs human review
    30  Failed
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from examforge import __version__


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(__version__, prog_name="examforge")
def main():
    """ExamForge: exam paper reconstruction pipeline."""
    pass


@main.command()
@click.option(
    "--exam", "-e",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the exam PDF file.",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["fast", "max"]),
    default="fast",
    help="Processing mode: fast (single engine) or max (dual engine).",
)
@click.option(
    "--spec",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to a custom spec YAML file. Uses default spec if not provided.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to examforge.yaml config file.",
)
@click.option("--debug", is_flag=True, help="Include provenance in HTML output.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
@click.option(
    "--max-pages",
    type=int,
    default=None,
    help="Process only the first N pages (for debugging).",
)
def execute(
    exam: Path,
    mode: str,
    spec: Path | None,
    config_path: Path | None,
    debug: bool,
    verbose: bool,
    max_pages: int | None,
):
    """Run the full pipeline on an exam PDF."""
    _setup_logging(verbose)
    logger = logging.getLogger("examforge.cli")

    # Load config
    from examforge.config import ExamForgeConfig

    overrides: dict = {"mode": mode, "debug": debug}
    if max_pages is not None:
        overrides["max_pages"] = max_pages

    config = ExamForgeConfig.load(config_path=config_path, overrides=overrides)

    # Load spec
    from examforge.spec import Spec

    if spec:
        spec_obj = Spec.load(spec)
    else:
        spec_obj = Spec.default()

    # Build stage pipeline
    stages = _build_stages(config)

    # Run
    from examforge.orchestrator.runner import PipelineRunner

    runner = PipelineRunner(stages=stages, config=config, spec=spec_obj)
    result = runner.execute(source_path=exam)

    # Report
    _print_summary(result)
    sys.exit(result.exit_code)


@main.command()
@click.option(
    "--run-id", "-r",
    required=True,
    help="The run ID to resume (timestamp_hash from the runs/ directory).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to examforge.yaml config file.",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def resume(run_id: str, config_path: Path | None, verbose: bool):
    """Resume a previously interrupted pipeline run."""
    _setup_logging(verbose)
    logger = logging.getLogger("examforge.cli")

    from examforge.config import ExamForgeConfig

    config = ExamForgeConfig.load(config_path=config_path)

    from examforge.spec import Spec

    spec_obj = Spec.default()

    stages = _build_stages(config)

    from examforge.orchestrator.runner import PipelineRunner

    runner = PipelineRunner(stages=stages, config=config, spec=spec_obj)
    result = runner.resume(run_id=run_id)

    _print_summary(result)
    sys.exit(result.exit_code)


@main.command()
@click.option(
    "--run-id", "-r",
    required=True,
    help="The run ID to inspect.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to examforge.yaml config file.",
)
def inspect(run_id: str, config_path: Path | None):
    """Show manifest and summary for a completed run."""
    from examforge.config import ExamForgeConfig

    config = ExamForgeConfig.load(config_path=config_path)
    manifest_path = config.paths.runs / run_id / "manifest.json"

    if not manifest_path.exists():
        click.echo(f"Run not found: {run_id}", err=True)
        sys.exit(1)

    data = json.loads(manifest_path.read_text())
    click.echo(json.dumps(data, indent=2, default=str))


def _build_stages(config):
    """Build the ordered list of pipeline stages."""
    from examforge.stages.s0_intake import S0Intake
    from examforge.stages.s3_parse import S3Parse
    from examforge.stages.s4_structure import S4Structure
    from examforge.stages.s6_figures import S6Figures
    from examforge.stages.s9_package import S9Package

    return [
        S0Intake(),
        S3Parse(),
        S4Structure(),
        S6Figures(),
        S9Package(),
    ]


def _print_summary(result):
    """Print a human-readable summary of the run result."""
    from examforge.orchestrator.runner import (
        EXIT_FAILED,
        EXIT_NEEDS_REVIEW,
        EXIT_OK,
        EXIT_WARNINGS,
    )

    summary = result.summary()
    status_icon = {
        EXIT_OK: "[OK]",
        EXIT_WARNINGS: "[WARN]",
        EXIT_NEEDS_REVIEW: "[REVIEW]",
        EXIT_FAILED: "[FAIL]",
    }.get(result.exit_code, "[?]")

    def _echo(msg: str = "") -> None:
        """click.echo with fallback for Windows cp1252 consoles."""
        try:
            click.echo(msg)
        except UnicodeEncodeError:
            click.echo(msg.encode("ascii", errors="replace").decode("ascii"))

    _echo()
    _echo(f"  {status_icon} Run {summary['run_id']} -- {summary['status']}")
    _echo(f"    Pages:     {summary['pages']}")
    _echo(f"    Questions: {summary['questions']}")
    _echo(f"    Issues:    {summary['issues']} ({summary['blockers']} blockers)")
    _echo(f"    Output:    {result.run_dir}")
    if summary.get("error"):
        _echo(f"    Error:     {summary['error']}")
    _echo()


if __name__ == "__main__":
    main()
