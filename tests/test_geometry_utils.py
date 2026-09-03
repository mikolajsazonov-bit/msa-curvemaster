#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testy jednostkowe dla modułu core.geometry_utils wtyczki MSA: CurveMaster.
"""

import math
import unittest
import os
import sys

# Dodaj ścieżkę do wtyczki
plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from core.geometry_utils import (
    SamplingMode,
    distance,
    arc_from_3_points,
    sample_arc,
    generate_bend_arc,
    fillet_corner,
    multi_vertex_fillet,
    fillet_between_segments,
    cyclic_range,
    replace_segment_in_points,
    replace_vertex_in_points,
    replace_vertex_range_in_points
)


class TestGeometryUtils(unittest.TestCase):

    def test_distance(self):
        p1 = (0.0, 0.0)
        p2 = (3.0, 4.0)
        self.assertAlmostEqual(distance(p1, p2), 5.0)

    def test_arc_from_3_points_semicircle(self):
        p1 = (-5.0, 0.0)
        p2 = (0.0, 5.0)
        p3 = (5.0, 0.0)

        res = arc_from_3_points(p1, p2, p3)
        self.assertIsNotNone(res)
        center, radius, a_start, a_end, is_ccw = res

        self.assertAlmostEqual(center[0], 0.0, places=5)
        self.assertAlmostEqual(center[1], 0.0, places=5)
        self.assertAlmostEqual(radius, 5.0, places=5)
        self.assertFalse(is_ccw)

    def test_sampling_modes(self):
        center = (0.0, 0.0)
        radius = 10.0
        start_angle = 0.0
        end_angle = math.pi / 2.0
        is_ccw = True

        pts_lin = sample_arc(center, radius, start_angle, end_angle, is_ccw,
                             mode=SamplingMode.LINEAR_STEP, step_value=2.0)
        self.assertGreaterEqual(len(pts_lin), 9)
        self.assertAlmostEqual(pts_lin[0][0], 10.0)
        self.assertAlmostEqual(pts_lin[0][1], 0.0)
        self.assertAlmostEqual(pts_lin[-1][0], 0.0)
        self.assertAlmostEqual(pts_lin[-1][1], 10.0)

    def test_fillet_corner_90_degrees(self):
        p_prev = (0.0, 10.0)
        p_curr = (0.0, 0.0)
        p_next = (10.0, 0.0)

        res = fillet_corner(p_prev, p_curr, p_next, radius=2.0, mode=SamplingMode.LINEAR_STEP, step_value=0.5)
        self.assertIsNotNone(res)
        t1, arc_pts, t2, center, eff_r, eff_d = res

        self.assertAlmostEqual(t1[0], 0.0)
        self.assertAlmostEqual(t1[1], 2.0)
        self.assertAlmostEqual(t2[0], 2.0)
        self.assertAlmostEqual(t2[0], 2.0)
        self.assertAlmostEqual(center[0], 2.0)
        self.assertAlmostEqual(center[1], 2.0)
        self.assertAlmostEqual(eff_r, 2.0)
        self.assertEqual(arc_pts[0], t1)
        self.assertEqual(arc_pts[-1], t2)

    def test_gentle_corner_next_to_sharp(self):
        pts = [
            (0.0, 50.0), # V0
            (0.0, 15.0), # V1
            (1.0, 0.0),  # V2
            (50.0, 0.0)  # V3
        ]

        # 1. Przeciąganie myszą na mały dystans (5m) -> modyfikuje tylko V1
        res_small = multi_vertex_fillet(pts, vertex_idx=1, drag_pt_or_radius=(5.0, 15.0), is_radius=False)
        self.assertIsNotNone(res_small)
        t1, arc_pts, t2, consumed, r, segs = res_small
        self.assertEqual(consumed, [1])
        self.assertEqual(segs, (0, 1))

        # 2. Przeciąganie myszą na duży dystans (20m) -> łączy V1 + V2
        res_large = multi_vertex_fillet(pts, vertex_idx=1, drag_pt_or_radius=(20.0, 15.0), is_radius=False)
        self.assertIsNotNone(res_large)
        t1_l, arc_pts_l, t2_l, consumed_l, r_l, segs_l = res_large
        self.assertEqual(consumed_l, [1, 2])
        self.assertEqual(segs_l, (0, 2))

        # 3. Wpisanie promienia dla aktywnego kontekstu segs_l=(0, 2)
        res_commit = fillet_between_segments(pts, a=0, b=2, radius=20.0)
        self.assertIsNotNone(res_commit)
        t1_c, arc_c, t2_c, consumed_c, r_c = res_commit
        self.assertEqual(consumed_c, [1, 2])
        self.assertAlmostEqual(r_c, 20.0)


    def test_cyclic_range(self):
        self.assertEqual(cyclic_range(1, 3, 4), [1, 2, 3])
        self.assertEqual(cyclic_range(2, 0, 4), [2, 3, 0])
        self.assertEqual(cyclic_range(1, 2, 4), [1, 2])
        self.assertEqual(cyclic_range(0, 0, 4), [0])

    def test_polygon_fillet_vertex_0(self):
        # Kwadrat 10x10 z wierzchołkiem 0 w punkcie (0, 0)
        square = [
            (0.0, 0.0),   # V0
            (10.0, 0.0),  # V1
            (10.0, 10.0), # V2
            (0.0, 10.0),  # V3
            (0.0, 0.0)    # V0
        ]
        # Zaokrąglenie narożnika V0 promieniem 2.0
        res = multi_vertex_fillet(square, vertex_idx=0, drag_pt_or_radius=2.0, is_radius=True, is_closed=True)
        self.assertIsNotNone(res)
        t1, arc_pts, t2, consumed, r, segs = res
        self.assertEqual(consumed, [0])
        self.assertAlmostEqual(r, 2.0)

        # Zamiana wierzchołka V0 w pierścieniu
        new_ring = replace_vertex_range_in_points(square, consumed_indices=consumed, replacement_points=arc_pts, is_closed=True)
        self.assertGreaterEqual(len(new_ring), 6)
        # Gwarancja domknięcia pierścienia
        self.assertEqual(new_ring[0], new_ring[-1])
        # Wierzchołki V1, V2, V3 powinny zachować swoje położenie
        self.assertIn((10.0, 0.0), new_ring)
        self.assertIn((10.0, 10.0), new_ring)
        self.assertIn((0.0, 10.0), new_ring)

    def test_polygon_fillet_intermediate_vertex(self):
        square = [
            (0.0, 0.0),   # V0
            (10.0, 0.0),  # V1
            (10.0, 10.0), # V2
            (0.0, 10.0),  # V3
            (0.0, 0.0)    # V0
        ]
        # Zaokrąglenie wierzchołka V1
        res = multi_vertex_fillet(square, vertex_idx=1, drag_pt_or_radius=2.0, is_radius=True, is_closed=True)
        self.assertIsNotNone(res)
        t1, arc_pts, t2, consumed, r, segs = res
        self.assertEqual(consumed, [1])

        new_ring = replace_vertex_range_in_points(square, consumed_indices=consumed, replacement_points=arc_pts, is_closed=True)
        self.assertEqual(new_ring[0], new_ring[-1])
        self.assertEqual(new_ring[0], (0.0, 0.0))  # V0 pozostaje na początku

    def test_polygon_multi_vertex_fillet_wrapping(self):
        # Wielokąt o małych załamaniach wokół wierzchołka 0
        poly = [
            (0.0, 0.0),    # V0
            (5.0, 0.0),    # V1
            (10.0, 1.0),   # V2
            (50.0, 1.0),   # V3
            (50.0, 50.0),  # V4
            (0.0, 50.0),   # V5
            (0.0, 5.0),    # V6
            (0.0, 0.0)     # V0
        ]
        # Duży promień na V0 połykający V6 i V1
        res = multi_vertex_fillet(poly, vertex_idx=0, drag_pt_or_radius=10.0, is_radius=True, is_closed=True)
        self.assertIsNotNone(res)
        t1, arc_pts, t2, consumed, r, segs = res
        self.assertIn(0, consumed)

        new_ring = replace_vertex_range_in_points(poly, consumed_indices=consumed, replacement_points=arc_pts, is_closed=True)
        self.assertEqual(new_ring[0], new_ring[-1])

    def test_polygon_replace_segment(self):
        square = [
            (0.0, 0.0),   # V0
            (10.0, 0.0),  # V1
            (10.0, 10.0), # V2
            (0.0, 10.0),  # V3
            (0.0, 0.0)    # V0
        ]
        # Wyginanie odcinka 0 (V0 -> V1)
        bend_pts = generate_bend_arc(square[0], (5.0, -2.0), square[1])
        new_ring_0 = replace_segment_in_points(square, seg_index=0, replacement=bend_pts, is_closed=True)
        self.assertEqual(new_ring_0[0], new_ring_0[-1])
        self.assertIn((5.0, -2.0), [(round(p[0], 1), round(p[1], 1)) for p in new_ring_0])

        # Wyginanie ostatniego odcinka (V3 -> V0)
        bend_pts_last = generate_bend_arc(square[3], (-2.0, 5.0), square[4])
        new_ring_last = replace_segment_in_points(square, seg_index=3, replacement=bend_pts_last, is_closed=True)
        self.assertEqual(new_ring_last[0], new_ring_last[-1])

    def test_polygon_fillet_between_segments_closed(self):
        square = [
            (0.0, 0.0),   # V0
            (10.0, 0.0),  # V1
            (10.0, 10.0), # V2
            (0.0, 10.0),  # V3
            (0.0, 0.0)    # V0
        ]
        # Fillet między segmentem 3 (V3->V0) a segmentem 0 (V0->V1) wokół V0
        res = fillet_between_segments(square, a=3, b=0, radius=2.0, is_closed=True)
        self.assertIsNotNone(res)
        t1, arc_pts, t2, consumed, r = res
        self.assertEqual(consumed, [0])
        self.assertAlmostEqual(r, 2.0)

        new_ring = replace_vertex_range_in_points(square, consumed_indices=consumed, replacement_points=arc_pts, is_closed=True)
        self.assertEqual(new_ring[0], new_ring[-1])

    def test_closed_triangle_fillet(self):
        # Trójkąt prostokątny
        triangle = [
            (0.0, 0.0),  # V0
            (10.0, 0.0), # V1
            (0.0, 10.0), # V2
            (0.0, 0.0)   # V0
        ]
        # Zaokrąglenie narożnika 90 stopni w V0
        res = multi_vertex_fillet(triangle, vertex_idx=0, drag_pt_or_radius=2.0, is_radius=True, is_closed=True)
        self.assertIsNotNone(res)
        t1, arc_pts, t2, consumed, r, segs = res
        self.assertEqual(consumed, [0])
        self.assertAlmostEqual(r, 2.0)

        new_ring = replace_vertex_range_in_points(triangle, consumed_indices=consumed, replacement_points=arc_pts, is_closed=True)
        self.assertEqual(new_ring[0], new_ring[-1])
        self.assertGreaterEqual(len(new_ring), 5)


if __name__ == '__main__':
    unittest.main()


