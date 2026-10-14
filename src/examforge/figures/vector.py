"""Vector-first figure extraction from digital PDFs via PyMuPDF get_drawings.

Provides:
- Union-find clustering of vector drawing primitives into diagrams.
- Cross-page path-signature hashing for watermark vector exclusion.
- Layout separator rule filtering (column rules, header/footer lines).
- Adaptive SVG (simple diagrams) vs high-DPI PNG (complex diagrams) rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any

import pymupdf

from examforge.figures.resolution import classify_scale_class, compute_target_dpi
from examforge.ir.schema import BBox, BlockStatus, Figure, FigureClass


@dataclass
class VectorCluster:
    """A cluster of vector drawings forming a single diagram candidate."""

    drawings: list[dict[str, Any]] = field(default_factory=list)
    bbox: BBox = field(default_factory=lambda: BBox(x1=0, y1=0, x2=0, y2=0))


def compute_path_signature(drawing: dict[str, Any]) -> str:
    """Compute a deterministic hash signature of a vector drawing's geometry."""
    items = drawing.get("items", [])
    w_val = drawing.get("width")
    width = round(float(w_val if w_val is not None else 1.0), 2)
    rect = drawing.get("rect")
    r_tuple = ()
    if rect is not None:
        r_tuple = (
            round(rect.x0, 1),
            round(rect.y0, 1),
            round(rect.x1, 1),
            round(rect.y1, 1),
        )

    # Serialize items
    item_parts = []
    for it in items:
        cmd = it[0]
        if cmd in ("l", "re"):
            item_parts.append(f"{cmd}:{it[1]}")
        elif cmd == "c":
            item_parts.append(f"c:{it[1]}:{it[2]}:{it[3]}:{it[4]}")
        else:
            item_parts.append(f"{cmd}")

    raw = f"{drawing.get('type')}|{width}|{r_tuple}|{','.join(item_parts)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def find_repeated_vector_signatures(
    doc: pymupdf.Document,
    min_pages: int = 3,
) -> set[str]:
    """Identify vector drawings that repeat identically across >= min_pages."""
    pages_by_sig: dict[str, set[int]] = {}

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        drawings = page.get_drawings()
        for d in drawings:
            sig = compute_path_signature(d)
            if sig not in pages_by_sig:
                pages_by_sig[sig] = set()
            pages_by_sig[sig].add(page_idx)

    repeated = {
        sig for sig, pages in pages_by_sig.items() if len(pages) >= min_pages
    }
    return repeated


def is_separator_rule(
    drawing: dict[str, Any],
    page_width: float,
    page_height: float,
) -> bool:
    """Return True if drawing is a full-width/height decorative or column rule."""
    rect = drawing.get("rect")
    if rect is None:
        return False

    w = rect.width
    h = rect.height

    # Horizontal separator rule
    if h <= 3.5 and w >= 0.45 * page_width:
        return True

    # Vertical column separator rule
    if w <= 3.5 and h >= 0.45 * page_height:
        return True

    return False


def _rect_distance(r1: pymupdf.Rect, r2: pymupdf.Rect) -> float:
    """Calculate minimum Euclidean distance between two bounding rectangles."""
    dx = max(0.0, max(r1.x0, r2.x0) - min(r1.x1, r2.x1))
    dy = max(0.0, max(r1.y0, r2.y0) - min(r1.y1, r2.y1))
    return (dx * dx + dy * dy) ** 0.5


def cluster_drawings(
    drawings: list[dict[str, Any]],
    distance_threshold: float = 20.0,
) -> list[VectorCluster]:
    """Group drawings within distance_threshold into VectorClusters using Union-Find."""
    if not drawings:
        return []

    n = len(drawings)
    parent = list(range(n))

    def find(i: int) -> int:
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i: int, j: int) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    rects = [d["rect"] for d in drawings]

    # Spatial grid index for O(N) neighbor lookup (Task O1.6)
    cell_size = max(distance_threshold, 40.0)
    grid: dict[tuple[int, int], list[int]] = {}

    for idx, r in enumerate(rects):
        # Range of grid cells covered by rect expanded by distance_threshold
        gx0 = int(r.x0 // cell_size)
        gy0 = int(r.y0 // cell_size)
        gx1 = int(r.x1 // cell_size)
        gy1 = int(r.y1 // cell_size)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                grid.setdefault((gx, gy), []).append(idx)

    # Check candidates only within neighboring grid cells
    checked_pairs: set[tuple[int, int]] = set()
    for idx, r in enumerate(rects):
        gx0 = int((r.x0 - distance_threshold) // cell_size)
        gy0 = int((r.y0 - distance_threshold) // cell_size)
        gx1 = int((r.x1 + distance_threshold) // cell_size)
        gy1 = int((r.y1 + distance_threshold) // cell_size)

        candidates: set[int] = set()
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                if (gx, gy) in grid:
                    candidates.update(grid[(gx, gy)])

        for cand in candidates:
            if cand > idx:
                pair = (idx, cand)
                if pair not in checked_pairs:
                    checked_pairs.add(pair)
                    if _rect_distance(rects[idx], rects[cand]) <= distance_threshold:
                        union(idx, cand)

    clusters_dict: dict[int, list[dict[str, Any]]] = {}
    for i in range(n):
        root = find(i)
        if root not in clusters_dict:
            clusters_dict[root] = []
        clusters_dict[root].append(drawings[i])

    result: list[VectorCluster] = []
    for group in clusters_dict.values():
        x0 = min(d["rect"].x0 for d in group)
        y0 = min(d["rect"].y0 for d in group)
        x1 = max(d["rect"].x1 for d in group)
        y1 = max(d["rect"].y1 for d in group)
        result.append(
            VectorCluster(
                drawings=group,
                bbox=BBox(
                    x1=int(round(x0)),
                    y1=int(round(y0)),
                    x2=int(round(x1)),
                    y2=int(round(y1)),
                ),
            )
        )

    return result


def extract_vector_figures(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    page_num: int,
    output_dir: Path,
    watermark_signatures: set[str] | None = None,
    distance_threshold: float = 20.0,
    min_dimension: int = 30,
    img_counter_start: int = 0,
) -> list[Figure]:
    """Extract clustered vector diagrams from a PDF page."""
    watermark_sigs = watermark_signatures or set()
    all_drawings = page.get_drawings()
    pw = page.rect.width
    ph = page.rect.height

    valid_drawings = []
    for d in all_drawings:
        sig = compute_path_signature(d)
        if sig in watermark_sigs:
            continue
        if is_separator_rule(d, pw, ph):
            continue
        rect = d.get("rect")
        if rect is None:
            continue
        # Skip footer rough work area
        if rect.y0 > ph * 0.90:
            continue
        valid_drawings.append(d)

    if not valid_drawings:
        return []

    clusters = cluster_drawings(valid_drawings, distance_threshold=distance_threshold)

    figures: list[Figure] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    counter = img_counter_start

    for cluster in clusters:
        bbox = cluster.bbox
        if bbox.width < min_dimension or bbox.height < min_dimension:
            continue

        fig_id = f"fig_vec_{page_num}_{counter}"
        counter += 1

        clip_rect = pymupdf.Rect(bbox.x1 - 2, bbox.y1 - 2, bbox.x2 + 2, bbox.y2 + 2)
        clip_rect.intersect(page.rect)

        # Decide whether to render SVG (simple) or high-DPI PNG (complex)
        is_simple = len(cluster.drawings) <= 60
        if is_simple:
            # Render SVG via 1-page subdocument
            fmt = "svg"
            crop_path = output_dir / f"{fig_id}.svg"
            temp_doc = pymupdf.open()
            temp_page = temp_doc.new_page(width=clip_rect.width, height=clip_rect.height)
            temp_page.show_pdf_page(
                pymupdf.Rect(0, 0, clip_rect.width, clip_rect.height),
                doc,
                page.number,
                clip=clip_rect,
            )
            svg_data = temp_page.get_svg_image()
            crop_path.write_text(svg_data, encoding="utf-8")
            temp_doc.close()
        else:
            fmt = "png"
            crop_path = output_dir / f"{fig_id}.png"
            target_dpi = compute_target_dpi(clip_rect.width, clip_rect.height)
            pix = page.get_pixmap(clip=clip_rect, dpi=target_dpi)
            pix.save(str(crop_path))

        width_mm = round((clip_rect.width / 72.0) * 25.4, 1)
        height_mm = round((clip_rect.height / 72.0) * 25.4, 1)
        scale_class = classify_scale_class(int(clip_rect.width), int(clip_rect.height))

        fig = Figure(
            id=fig_id,
            page=page_num,
            bbox=BBox(
                x1=int(round(clip_rect.x0)),
                y1=int(round(clip_rect.y0)),
                x2=int(round(clip_rect.x1)),
                y2=int(round(clip_rect.y1)),
            ),
            crop_path=str(crop_path),
            format=fmt,
            classification=FigureClass.DIAGRAM,
            scale_class=scale_class,
            width_mm=width_mm,
            height_mm=height_mm,
            status=BlockStatus.TRUSTED,
        )
        figures.append(fig)

    return figures
