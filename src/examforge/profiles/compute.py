"""
Compute tier configuration and auto-detection for ExamForge v2.

Defines resources and engine policies for:
- lite: memory-constrained environments, CI runners (120 DPI, 1 worker, 25 MP)
- standard: standard CPU multi-core machines (150 DPI, ⌊CPU/2⌋ workers, 60 MP)
- gpu: GPU-accelerated workstations / cloud runners (150 DPI, ⌊CPU/2⌋ workers, 120 MP)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

ComputeTierName = Literal["lite", "standard", "gpu"]
COMPUTE_DIR = Path(__file__).parent / "compute"


class ComputeTierConfig(BaseModel):
    """Execution resources and device policies for a pipeline run."""

    model_config = ConfigDict(frozen=True)

    tier: ComputeTierName = "standard"
    dpi: int = 150
    workers: int = Field(default_factory=lambda: max(1, (os.cpu_count() or 2) // 2))
    max_image_pixels: int = 60_000_000
    second_ocr: Literal["on_demand", "on_low_confidence", "always"] = "on_low_confidence"
    paddle_device: Literal["cpu", "gpu"] = "cpu"
    bank_embeddings: bool = False


def load_compute_tier(tier: ComputeTierName) -> ComputeTierConfig:
    """Load compute tier configuration from YAML file or defaults."""
    yaml_path = COMPUTE_DIR / f"{tier}.yaml"
    if yaml_path.is_file():
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # Resolve dynamic workers if specified as 'cpu/2'
            if data.get("workers") == "auto":
                cpu_cnt = os.cpu_count() or 2
                data["workers"] = 1 if tier == "lite" else max(1, cpu_cnt // 2)
            return ComputeTierConfig.model_validate(data)

    # Defaults per §6 table
    if tier == "lite":
        return ComputeTierConfig(
            tier="lite",
            dpi=120,
            workers=1,
            max_image_pixels=25_000_000,
            second_ocr="on_demand",
            paddle_device="cpu",
            bank_embeddings=False,
        )
    if tier == "gpu":
        cpu_cnt = os.cpu_count() or 2
        return ComputeTierConfig(
            tier="gpu",
            dpi=150,
            workers=max(1, cpu_cnt // 2),
            max_image_pixels=120_000_000,
            second_ocr="on_low_confidence",
            paddle_device="gpu",
            bank_embeddings=True,
        )

    # standard
    cpu_cnt = os.cpu_count() or 2
    return ComputeTierConfig(
        tier="standard",
        dpi=150,
        workers=max(1, cpu_cnt // 2),
        max_image_pixels=60_000_000,
        second_ocr="on_low_confidence",
        paddle_device="cpu",
        bank_embeddings=False,
    )


def resolve_compute_tier(requested: str | None = None) -> ComputeTierConfig:
    """
    Select compute tier explicitly or auto-detect based on host capabilities.
    """
    if requested and requested in ("lite", "standard", "gpu"):
        return load_compute_tier(requested)  # type: ignore

    # Auto-detection heuristic:
    # If host CPU count is 1 or memory is limited, choose lite
    cpu_cnt = os.cpu_count() or 1
    if cpu_cnt <= 1:
        return load_compute_tier("lite")

    return load_compute_tier("standard")


def calculate_thread_budget(
    tier: ComputeTierName = "standard",
    cpu_count: int | None = None,
    ram_gb: float | None = None,
) -> tuple[int, int]:
    """
    Compute (workers, threads_per_worker) honoring workers * threads <= cpu_count.
    Rule:
      workers = min(cpu // 2, ram_gb // 2) (min 1, on lite: 1)
      threads_per_worker = max(1, cpu // workers)
    """
    cpus = cpu_count or os.cpu_count() or 2
    if tier == "lite" or cpus <= 1:
        return (1, max(1, cpus))

    if ram_gb is not None:
        max_workers_by_ram = max(1, int(ram_gb // 2))
        workers = min(max(1, cpus // 2), max_workers_by_ram)
    else:
        workers = max(1, cpus // 2)

    threads_per_worker = max(1, cpus // workers)
    while workers * threads_per_worker > cpus and threads_per_worker > 1:
        threads_per_worker -= 1

    return (workers, threads_per_worker)


def apply_thread_budget(
    tier: ComputeTierName = "standard",
    cpu_count: int | None = None,
    ram_gb: float | None = None,
) -> tuple[int, int]:
    """Calculate and set environment and library thread limits."""
    workers, threads = calculate_thread_budget(tier, cpu_count, ram_gb)
    t_str = str(threads)
    os.environ["OMP_NUM_THREADS"] = t_str
    os.environ["MKL_NUM_THREADS"] = t_str
    os.environ["OPENBLAS_NUM_THREADS"] = t_str
    os.environ["VECLIB_MAXIMUM_THREADS"] = t_str
    os.environ["NUMEXPR_NUM_THREADS"] = t_str

    try:
        import cv2

        cv2.setNumThreads(threads)
    except Exception:
        pass

    return (workers, threads)
