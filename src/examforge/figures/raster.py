"""Raster figure extraction for scanned pages using connected-component clustering."""

from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image

from examforge.figures.cleanup import remove_black_borders
from examforge.figures.crop import refine_bbox
from examforge.figures.resolution import classify_scale_class
from examforge.ir.schema import BBox, BlockStatus, Figure, FigureClass


class _DisjointSet:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, i: int) -> int:
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i: int, j: int) -> None:
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j


def extract_raster_components(
    image: Image.Image | np.ndarray,
    ink_threshold: int = 200,
    min_pixels: int = 150,
) -> list[tuple[int, int, int, int, int]]:
    """Extract connected components as (x1, y1, x2, y2, pixel_count) tuples."""
    if isinstance(image, Image.Image):
        arr = np.array(image.convert("L"))
    else:
        arr = image if image.ndim == 2 else np.array(Image.fromarray(image).convert("L"))

    h, w = arr.shape
    binary = arr < ink_threshold

    # Run-length encoding per row
    runs_by_row: list[list[tuple[int, int, int]]] = []
    run_boxes: dict[int, list[int]] = {}  # run_id -> [x1, y1, x2, y2, count]
    run_id = 0

    for y in range(h):
        row = binary[y]
        diff = np.diff(np.pad(row.astype(np.int8), (1, 1), "constant"))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        row_runs: list[tuple[int, int, int]] = []
        for s, e in zip(starts, ends):
            rid = run_id
            run_id += 1
            run_boxes[rid] = [int(s), int(y), int(e - 1), int(y), int(e - s)]
            row_runs.append((int(s), int(e - 1), rid))

        runs_by_row.append(row_runs)

    if run_id == 0:
        return []

    dsu = _DisjointSet(run_id)

    # Connect adjacent rows (8-connectivity)
    for y in range(1, h):
        curr_runs = runs_by_row[y]
        prev_runs = runs_by_row[y - 1]
        if not curr_runs or not prev_runs:
            continue
        for s1, e1, r1 in curr_runs:
            for s0, e0, r0 in prev_runs:
                if max(s1, s0) <= min(e1, e0) + 1 and min(s1, s0) <= max(e1, e0) + 1:
                    dsu.union(r1, r0)

    # Aggregate by root
    clusters: dict[int, list[int]] = {}
    for rid in range(run_id):
        root = dsu.find(rid)
        if root not in clusters:
            clusters[root] = list(run_boxes[rid])
        else:
            b = clusters[root]
            rb = run_boxes[rid]
            b[0] = min(b[0], rb[0])
            b[1] = min(b[1], rb[1])
            b[2] = max(b[2], rb[2])
            b[3] = max(b[3], rb[3])
            b[4] += rb[4]

    valid_components = []
    for c in clusters.values():
        x1, y1, x2, y2, count = c
        if count >= min_pixels:
            valid_components.append((x1, y1, x2, y2, count))

    return valid_components


def extract_raster_figures(
    page_image: Image.Image,
    page_num: int,
    output_dir: Path,
    min_dimension: int = 45,
    max_aspect_ratio: float = 6.0,
    img_counter_start: int = 0,
) -> list[Figure]:
    """Extract raster diagram crops from a scanned page image."""
    output_dir.mkdir(parents=True, exist_ok=True)
    w, h = page_image.size

    components = extract_raster_components(page_image)
    if not components:
        return []

    figures: list[Figure] = []
    counter = img_counter_start

    # Merge nearby components
    merged_boxes: list[BBox] = []
    for x1, y1, x2, y2, _ in components:
        bw = x2 - x1
        bh = y2 - y1
        if bw < min_dimension and bh < min_dimension:
            continue
        aspect = max(bw / max(1, bh), bh / max(1, bw))
        if aspect > max_aspect_ratio:
            continue
        # Skip footer rough work
        if y1 > h * 0.90:
            continue

        bbox = BBox(x1=x1, y1=y1, x2=x2, y2=y2)
        # Check merge with existing
        merged = False
        for i, existing in enumerate(merged_boxes):
            dx = max(0, max(existing.x1, bbox.x1) - min(existing.x2, bbox.x2))
            dy = max(0, max(existing.y1, bbox.y1) - min(existing.y2, bbox.y2))
            if dx <= 25 and dy <= 25:
                merged_boxes[i] = BBox(
                    x1=min(existing.x1, bbox.x1),
                    y1=min(existing.y1, bbox.y1),
                    x2=max(existing.x2, bbox.x2),
                    y2=max(existing.y2, bbox.y2),
                )
                merged = True
                break
        if not merged:
            merged_boxes.append(bbox)

    for box in merged_boxes:
        refined = refine_bbox(page_image, box, page_width=w, page_height=h)
        crop_im = page_image.crop((refined.x1, refined.y1, refined.x2, refined.y2))
        clean_crop, _ = remove_black_borders(crop_im)

        fig_id = f"fig_rst_{page_num}_{counter}"
        counter += 1
        crop_path = output_dir / f"{fig_id}.png"
        clean_crop.save(str(crop_path))

        scale_class = classify_scale_class(clean_crop.width, clean_crop.height)
        width_mm = round((clean_crop.width / 300.0) * 25.4, 1)  # assume 300 dpi scan
        height_mm = round((clean_crop.height / 300.0) * 25.4, 1)

        fig = Figure(
            id=fig_id,
            page=page_num,
            bbox=refined,
            crop_path=str(crop_path),
            format="png",
            classification=FigureClass.DIAGRAM,
            scale_class=scale_class,
            width_mm=width_mm,
            height_mm=height_mm,
            status=BlockStatus.TRUSTED,
        )
        figures.append(fig)

    return figures
