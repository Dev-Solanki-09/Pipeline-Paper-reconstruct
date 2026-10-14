"""Tests for synthetic figure generator."""

from __future__ import annotations

import numpy as np
from PIL import Image

from examforge.synth.figures import (
    draw_circuit_diagram,
    draw_coordinate_graph,
    draw_mechanics_pulley,
    draw_ray_diagram,
    generate_figure,
)


def test_draw_circuit_diagram():
    im = draw_circuit_diagram(width=300, height=200)
    assert isinstance(im, Image.Image)
    assert im.size == (300, 200)
    arr = np.array(im)
    # Check that image is not purely white
    assert np.any(arr < 200)


def test_draw_ray_diagram():
    im = draw_ray_diagram(width=350, height=220)
    assert im.size == (350, 220)
    arr = np.array(im)
    assert np.any(arr < 200)


def test_draw_coordinate_graph():
    im = draw_coordinate_graph(width=400, height=240)
    assert im.size == (400, 240)
    arr = np.array(im)
    assert np.any(arr < 200)


def test_draw_mechanics_pulley():
    im = draw_mechanics_pulley(width=320, height=200)
    assert im.size == (320, 200)
    arr = np.array(im)
    assert np.any(arr < 200)


def test_generate_figure_dispatcher():
    for kind in ["circuit", "ray", "graph", "pulley"]:
        im = generate_figure(kind=kind, width=250, height=180)
        assert im.size == (250, 180)
