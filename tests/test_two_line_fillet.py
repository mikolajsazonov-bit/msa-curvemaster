#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testy jednostkowe dla algorytmu zaokrąglania dwóch linii (Fillet) w core.geometry_utils.
"""

import math
import unittest
import os
import sys

plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from core.geometry_utils import (
    fillet_two_lines_2d,
    SamplingMode,
    distance
)


class TestTwoLineFilletGeometry(unittest.TestCase):

    def test_corner_fillet_90_deg(self):
        # Linia 1: pionowa od (0, 10) do (0, 0)
        pts1 = [(0.0, 10.0), (0.0, 0.0)]
        click1 = (0.0, 5.0)

        # Linia 2: pozioma od (10, 0) do (0, 0)
        pts2 = [(10.0, 0.0), (0.0, 0.0)]
        click2 = (5.0, 0.0)

        res = fillet_two_lines_2d(pts1, click1, pts2, click2, radius=2.0)
        self.assertIsNotNone(res)

        self.assertAlmostEqual(res.apex[0], 0.0)
        self.assertAlmostEqual(res.apex[1], 0.0)
        self.assertAlmostEqual(res.radius, 2.0)

        # Punkty styczności: T1=(0, 2), T2=(2, 0)
        self.assertAlmostEqual(res.t1[0], 0.0)
        self.assertAlmostEqual(res.t1[1], 2.0)
        self.assertAlmostEqual(res.t2[0], 2.0)
        self.assertAlmostEqual(res.t2[1], 0.0)

        # Żadna linia nie kontynuuje się za (0, 0)
        self.assertFalse(res.line1_continues)
        self.assertFalse(res.line2_continues)

        # Scalona polilinia narożnika powinna łączyć (0, 10) -> (0, 2) -> łuk -> (2, 0) -> (10, 0)
        self.assertIsNotNone(res.joined_corner)
        self.assertAlmostEqual(res.joined_corner[0][0], 0.0)
        self.assertAlmostEqual(res.joined_corner[0][1], 10.0)
        self.assertAlmostEqual(res.joined_corner[-1][0], 10.0)
        self.assertAlmostEqual(res.joined_corner[-1][1], 0.0)

    def test_through_line_fillet(self):
        # Linia 1 jest linią przelotową od (0, 20) do (0, -20) (przechodzi przez 0, 0)
        pts1 = [(0.0, 20.0), (0.0, -20.0)]
        # Klikamy na część górną (y = 10)
        click1 = (0.0, 10.0)

        # Linia 2 dochodzi od prawej: (20, 0) do (0, 0)
        pts2 = [(20.0, 0.0), (0.0, 0.0)]
        click2 = (10.0, 0.0)

        res = fillet_two_lines_2d(pts1, click1, pts2, click2, radius=5.0)
        self.assertIsNotNone(res)

        # Linia 1 powinna zostać oznaczona jako posiadająca kontynuację
        self.assertTrue(res.line1_continues)
        self.assertIsNotNone(res.line1_continuation)

        # Część zachowana linii 1 kończy się na T1 = (0, 5)
        self.assertAlmostEqual(res.line1_kept[-1][0], 0.0)
        self.assertAlmostEqual(res.line1_kept[-1][1], 5.0)

        # Część kontynuacji linii 1 zaczyna się w apex=(0, 0) i biegnie do (0, -20)
        self.assertAlmostEqual(res.line1_continuation[0][0], 0.0)
        self.assertAlmostEqual(res.line1_continuation[0][1], 0.0)
        self.assertAlmostEqual(res.line1_continuation[-1][0], 0.0)
        self.assertAlmostEqual(res.line1_continuation[-1][1], -20.0)

        # Linia 2 nie ma kontynuacji
        self.assertFalse(res.line2_continues)

    def test_parallel_lines_no_fillet(self):
        pts1 = [(0.0, 0.0), (10.0, 0.0)]
        pts2 = [(0.0, 5.0), (10.0, 5.0)]
        res = fillet_two_lines_2d(pts1, (5.0, 0.0), pts2, (5.0, 5.0), radius=2.0)
        self.assertIsNone(res)


if __name__ == '__main__':
    unittest.main()
