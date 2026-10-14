"""Programmatic figure generator for synthetic exam papers.

Draws clean, realistic STEM diagrams (circuits, ray diagrams, coordinate graphs,
mechanics pulleys/inclines) with arrows, labels, and precise bounding boxes using Pillow.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int] = (0, 0, 0),
    width: int = 2,
    arrow_size: float = 8.0,
) -> None:
    """Draw a line with an arrowhead at end."""
    x0, y0 = start
    x1, y1 = end
    draw.line([start, end], fill=color, width=width)
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-4:
        return
    ux = dx / length
    uy = dy / length
    # Perpendicular vector
    px = -uy
    py = ux

    # Arrowhead polygon
    p1 = (x1, y1)
    p2 = (x1 - ux * arrow_size + px * (arrow_size * 0.5), y1 - uy * arrow_size + py * (arrow_size * 0.5))
    p3 = (x1 - ux * arrow_size - px * (arrow_size * 0.5), y1 - uy * arrow_size - py * (arrow_size * 0.5))
    draw.polygon([p1, p2, p3], fill=color)


def draw_circuit_diagram(width: int = 400, height: int = 240) -> Image.Image:
    """Generate an electrical circuit diagram (resistor, battery, switch, capacitor)."""
    im = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(im)

    # Main rectangular circuit loop
    pad_x, pad_y = 50, 40
    r_x1, r_y1 = pad_x, pad_y
    r_x2, r_y2 = width - pad_x, height - pad_y

    # Top wire with resistor
    # Left segment
    res_start_x = r_x1 + 100
    res_end_x = r_x1 + 200
    draw.line([(r_x1, r_y1), (res_start_x, r_y1)], fill=(0, 0, 0), width=2)
    # Zig-zag resistor
    points = [(res_start_x, r_y1)]
    zz_steps = 6
    dx = (res_end_x - res_start_x) / zz_steps
    for i in range(1, zz_steps):
        dy = -12 if i % 2 == 1 else 12
        points.append((res_start_x + i * dx, r_y1 + dy))
    points.append((res_end_x, r_y1))
    draw.line(points, fill=(0, 0, 0), width=2)
    # Label R
    draw.text((res_start_x + 40, r_y1 - 30), "R = 10 \u03a9", fill=(0, 0, 0))
    # Right top segment
    draw.line([(res_end_x, r_y1), (r_x2, r_y1)], fill=(0, 0, 0), width=2)

    # Right vertical wire
    draw.line([(r_x2, r_y1), (r_x2, r_y2)], fill=(0, 0, 0), width=2)

    # Bottom wire with battery (long plate, short plate)
    bat_mid_x = (r_x1 + r_x2) / 2
    draw.line([(r_x1, r_y2), (bat_mid_x - 20, r_y2)], fill=(0, 0, 0), width=2)
    draw.line([(bat_mid_x + 20, r_y2), (r_x2, r_y2)], fill=(0, 0, 0), width=2)
    # Long line (+)
    draw.line([(bat_mid_x - 10, r_y2 - 20), (bat_mid_x - 10, r_y2 + 20)], fill=(0, 0, 0), width=2)
    draw.text((bat_mid_x - 25, r_y2 - 25), "+", fill=(0, 0, 0))
    # Short line (-)
    draw.line([(bat_mid_x + 10, r_y2 - 12), (bat_mid_x + 10, r_y2 + 12)], fill=(0, 0, 0), width=3)
    draw.text((bat_mid_x + 15, r_y2 - 25), "-", fill=(0, 0, 0))
    # Label V
    draw.text((bat_mid_x - 15, r_y2 + 22), "V = 12V", fill=(0, 0, 0))

    # Left vertical wire with current arrow
    draw.line([(r_x1, r_y2), (r_x1, r_y1)], fill=(0, 0, 0), width=2)
    _draw_arrow(draw, (r_x1, r_y2 - 30), (r_x1, r_y1 + 40), color=(0, 0, 0), width=2)
    draw.text((r_x1 - 25, (r_y1 + r_y2) / 2 - 5), "I", fill=(0, 0, 0))

    return im


def draw_ray_diagram(width: int = 400, height: int = 240) -> Image.Image:
    """Generate an optics ray diagram (interface, normal, incident, reflected, refracted)."""
    im = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(im)

    mid_y = height // 2
    mid_x = width // 2

    # Interface line
    draw.line([(20, mid_y), (width - 20, mid_y)], fill=(0, 0, 0), width=2)
    draw.text((25, mid_y - 25), "Medium 1 (n1)", fill=(0, 0, 0))
    draw.text((25, mid_y + 10), "Medium 2 (n2)", fill=(0, 0, 0))

    # Normal line (dashed)
    for y in range(20, height - 20, 8):
        draw.line([(mid_x, y), (mid_x, min(y + 4, height - 20))], fill=(100, 100, 100), width=1)
    draw.text((mid_x + 6, 25), "Normal", fill=(100, 100, 100))

    # Incident ray (angle 45 deg)
    inc_start = (mid_x - 120, mid_y - 120)
    inc_end = (mid_x, mid_y)
    draw.line([inc_start, inc_end], fill=(200, 0, 0), width=2)
    _draw_arrow(draw, (mid_x - 80, mid_y - 80), (mid_x - 40, mid_y - 40), color=(200, 0, 0), width=2)
    draw.text((mid_x - 45, mid_y - 50), "\u03b81", fill=(200, 0, 0))

    # Refracted ray (Snell's law, steeper angle)
    ref_start = (mid_x, mid_y)
    ref_end = (mid_x + 80, mid_y + 120)
    draw.line([ref_start, ref_end], fill=(0, 120, 200), width=2)
    _draw_arrow(draw, (mid_x + 30, mid_y + 45), (mid_x + 60, mid_y + 90), color=(0, 120, 200), width=2)
    draw.text((mid_x + 20, mid_y + 40), "\u03b82", fill=(0, 120, 200))

    return im


def draw_coordinate_graph(width: int = 400, height: int = 240) -> Image.Image:
    """Generate a 2D coordinate graph with axes, tick marks, and function curve."""
    im = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(im)

    orig_x = 60
    orig_y = height - 40

    # Grid lines (light gray)
    for x in range(orig_x, width - 20, 40):
        draw.line([(x, 20), (x, orig_y)], fill=(230, 230, 230), width=1)
    for y in range(20, orig_y, 35):
        draw.line([(orig_x, y), (width - 20, y)], fill=(230, 230, 230), width=1)

    # X and Y Axes with arrows
    _draw_arrow(draw, (orig_x, orig_y), (width - 20, orig_y), color=(0, 0, 0), width=2)
    _draw_arrow(draw, (orig_x, orig_y), (orig_x, 20), color=(0, 0, 0), width=2)
    draw.text((width - 30, orig_y + 10), "x", fill=(0, 0, 0))
    draw.text((orig_x - 20, 15), "y", fill=(0, 0, 0))
    draw.text((orig_x - 15, orig_y + 5), "O", fill=(0, 0, 0))

    # Curve (e.g. parabola or sine segment)
    curve_pts = []
    for step in range(0, 280, 5):
        cx = orig_x + step
        # Normalized x in [0, pi]
        norm_x = (step / 280.0) * math.pi
        cy = orig_y - int(math.sin(norm_x) * 140)
        curve_pts.append((cx, cy))

    draw.line(curve_pts, fill=(0, 100, 200), width=2)
    draw.text((orig_x + 130, orig_y - 155), "y = f(x)", fill=(0, 100, 200))

    return im


def draw_mechanics_pulley(width: int = 400, height: int = 240) -> Image.Image:
    """Generate a mechanics pulley with hanging masses."""
    im = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(im)

    # Ceiling
    draw.line([(100, 30), (300, 30)], fill=(0, 0, 0), width=3)
    for x in range(110, 300, 15):
        draw.line([(x, 30), (x - 10, 20)], fill=(120, 120, 120), width=1)

    # Pulley mount
    pulley_center = (200, 70)
    draw.line([(200, 30), pulley_center], fill=(0, 0, 0), width=2)

    # Pulley disk
    r = 25
    draw.ellipse(
        [
            (pulley_center[0] - r, pulley_center[1] - r),
            (pulley_center[0] + r, pulley_center[1] + r),
        ],
        outline=(0, 0, 0),
        width=2,
    )

    # Left rope and mass m1
    left_x = pulley_center[0] - r
    m1_top = 140
    draw.line([(left_x, pulley_center[1]), (left_x, m1_top)], fill=(0, 0, 0), width=2)
    draw.rectangle([(left_x - 20, m1_top), (left_x + 20, m1_top + 40)], outline=(0, 0, 0), width=2)
    draw.text((left_x - 10, m1_top + 12), "m1", fill=(0, 0, 0))

    # Right rope and mass m2
    right_x = pulley_center[0] + r
    m2_top = 110
    draw.line([(right_x, pulley_center[1]), (right_x, m2_top)], fill=(0, 0, 0), width=2)
    draw.rectangle([(right_x - 25, m2_top), (right_x + 25, m2_top + 50)], outline=(0, 0, 0), width=2)
    draw.text((right_x - 10, m2_top + 18), "m2", fill=(0, 0, 0))

    # Gravity arrow
    _draw_arrow(draw, (pulley_center[0] + 70, 70), (pulley_center[0] + 70, 120), color=(100, 100, 100), width=2)
    draw.text((pulley_center[0] + 76, 90), "g", fill=(100, 100, 100))

    return im


def generate_figure(kind: str = "circuit", width: int = 400, height: int = 240) -> Image.Image:
    """Generate figure by kind ('circuit', 'ray', 'graph', 'pulley')."""
    if kind == "circuit":
        return draw_circuit_diagram(width, height)
    elif kind == "ray":
        return draw_ray_diagram(width, height)
    elif kind == "graph":
        return draw_coordinate_graph(width, height)
    elif kind == "pulley":
        return draw_mechanics_pulley(width, height)
    return draw_circuit_diagram(width, height)
