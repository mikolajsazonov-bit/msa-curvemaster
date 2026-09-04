#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testy jednostkowe dla algorytmów Trim / Extend w core.geometry_utils.
"""

import math
import unittest
import os
import sys

plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from core.geometry_utils import (
    ray_polyline_intersection,
    trim_polyline_with_boundaries,
    segment_intersection_2d,
    distance
)


class TestTrimExtendGeometry(unittest.TestCase):

    def test_segment_intersection(self):
        # Odcinki prostopadłe przecinające się w (5, 5)
        p1 = (0.0, 5.0)
        p2 = (10.0, 5.0)
        p3 = (5.0, 0.0)
        p4 = (5.0, 10.0)

        res = segment_intersection_2d(p1, p2, p3, p4)
        self.assertIsNotNone(res)
        t, u, ipt = res
        self.assertAlmostEqual(ipt[0], 5.0)
        self.assertAlmostEqual(ipt[1], 5.0)

    def test_ray_polyline_intersection(self):
        origin = (0.0, 0.0)
        ray_dir = (1.0, 0.0) # w prawo wzdłuż osi X

        # Polilinia tworząca pionową ścianę x = 10 od y = -5 do y = 5
        polyline = [(10.0, -5.0), (10.0, 5.0)]

        res = ray_polyline_intersection(origin, ray_dir, polyline)
        self.assertIsNotNone(res)
        dist_t, ipt = res
        self.assertAlmostEqual(dist_t, 10.0)
        self.assertAlmostEqual(ipt[0], 10.0)
        self.assertAlmostEqual(ipt[1], 0.0)

    def test_ray_polyline_intersection_multiple_segments(self):
        origin = (0.0, 0.0)
        ray_dir = (0.0, 1.0) # w górę

        # Polilinia w kształcie zygzaka przecinająca oś Y na y = 15 i y = 30
        polyline = [
            (-10.0, 15.0), (10.0, 15.0),
            (10.0, 30.0), (-10.0, 30.0)
        ]

        res = ray_polyline_intersection(origin, ray_dir, polyline)
        self.assertIsNotNone(res)
        dist_t, ipt = res
        self.assertAlmostEqual(dist_t, 15.0)
        self.assertAlmostEqual(ipt[0], 0.0)
        self.assertAlmostEqual(ipt[1], 15.0)

    def test_trim_end_overhang(self):
        # Linia pozioma od 0 do 20 na y = 5
        line = [(0.0, 5.0), (20.0, 5.0)]
        # Krawędź tnąca pionowa x = 15 od 0 do 10
        boundary = [[(15.0, 0.0), (15.0, 10.0)]]

        # Klikamy na nawis po prawej (np. x = 18, y = 5)
        click_pt = (18.0, 5.0)
        res = trim_polyline_with_boundaries(line, boundary, click_pt)
        self.assertIsNotNone(res)
        trimmed, remaining = res

        # Usunięty fragment to (15, 5) -> (20, 5)
        self.assertAlmostEqual(trimmed[0][0], 15.0)
        self.assertAlmostEqual(trimmed[-1][0], 20.0)

        # Pozostały fragment to (0, 5) -> (15, 5)
        self.assertEqual(len(remaining), 1)
        self.assertAlmostEqual(remaining[0][0][0], 0.0)
        self.assertAlmostEqual(remaining[0][-1][0], 15.0)

    def test_trim_start_overhang(self):
        line = [(0.0, 5.0), (20.0, 5.0)]
        boundary = [[(5.0, 0.0), (5.0, 10.0)]]

        # Klikamy na nawis po lewej (x = 2, y = 5)
        click_pt = (2.0, 5.0)
        res = trim_polyline_with_boundaries(line, boundary, click_pt)
        self.assertIsNotNone(res)
        trimmed, remaining = res

        # Usunięty: (0, 5) -> (5, 5)
        self.assertAlmostEqual(trimmed[0][0], 0.0)
        self.assertAlmostEqual(trimmed[-1][0], 5.0)

        # Pozostały: (5, 5) -> (20, 5)
        self.assertEqual(len(remaining), 1)
        self.assertAlmostEqual(remaining[0][0][0], 5.0)
        self.assertAlmostEqual(remaining[0][-1][0], 20.0)

    def test_trim_interior_segment(self):
        # Linia od 0 do 30
        line = [(0.0, 0.0), (30.0, 0.0)]
        # Dwie krawędzie tnące: na x = 10 i na x = 20
        boundaries = [
            [(10.0, -5.0), (10.0, 5.0)],
            [(20.0, -5.0), (20.0, 5.0)]
        ]

        # Klikamy w środek: x = 15
        click_pt = (15.0, 0.0)
        res = trim_polyline_with_boundaries(line, boundaries, click_pt)
        self.assertIsNotNone(res)
        trimmed, remaining = res

        # Usunięty: (10, 0) -> (20, 0)
        self.assertAlmostEqual(trimmed[0][0], 10.0)
        self.assertAlmostEqual(trimmed[-1][0], 20.0)

        # Pozostały: dwa fragmenty: (0, 0)->(10, 0) oraz (20, 0)->(30, 0)
        self.assertEqual(len(remaining), 2)
        self.assertAlmostEqual(remaining[0][0][0], 0.0)
        self.assertAlmostEqual(remaining[0][-1][0], 10.0)
        self.assertAlmostEqual(remaining[1][0][0], 20.0)
        self.assertAlmostEqual(remaining[1][-1][0], 30.0)


    def test_copy_attributes_for_new_feature(self):
        from qgis.core import QgsFields, QgsField, QgsFeature, QgsVectorLayer
        from qgis.PyQt.QtCore import QVariant
        from core.layer_modifier import LayerModifier

        lyr = QgsVectorLayer("LineString?crs=epsg:4326&field=fid:integer&field=name:string", "test", "memory")
        f = QgsFeature(lyr.fields())
        f.setAttributes([42, "Ulica"])

        copied = LayerModifier.copy_attributes_for_new_feature(lyr, f)
        # fid powinien być wyzerowany do None/NULL, a inne atrybuty zachowane
        self.assertIsNone(copied[0])
        self.assertEqual(copied[1], "Ulica")


if __name__ == '__main__':
    unittest.main()
