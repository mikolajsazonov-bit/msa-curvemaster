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

    def test_same_line_loop_closing_island(self):
        # Wyspa/pętla o 11 wierzchołkach, której końce schodzą się w ostry dziób
        island_pts = [
            (9.0, -0.2),
            (5.0, -1.0),
            (0.0, -2.0),
            (-10.0, -2.0),
            (-20.0, -2.0),
            (-25.0, 0.0),
            (-20.0, 2.0),
            (-10.0, 2.0),
            (0.0, 2.0),
            (5.0, 1.0),
            (9.0, 0.2)
        ]
        # Klikamy na ramiona zbliżające się do dzioba
        click1 = (7.0, 0.6)   # segment 9: (5, 1) -> (9, 0.2)
        click2 = (7.0, -0.6)  # segment 0: (9, -0.2) -> (5, -1)

        res = fillet_two_lines_2d(
            pts1=island_pts,
            click1=click1,
            pts2=island_pts,
            click2=click2,
            radius=2.0,
            is_same_line=True
        )

        self.assertIsNotNone(res)
        self.assertFalse(res.line1_continues)
        self.assertFalse(res.line2_continues)
        self.assertIsNotNone(res.joined_corner)

        # Sprawdzamy czy cała wyspa została zachowana (min. 10 punktów, a nie tylko 2-punktowy obcięty dziób)
        self.assertGreaterEqual(len(res.joined_corner), 10)

        # Sprawdzamy domknięcie pętli (pierwszy punkt równy ostatniemu)
        self.assertAlmostEqual(res.joined_corner[0][0], res.joined_corner[-1][0], places=3)
        self.assertAlmostEqual(res.joined_corner[0][1], res.joined_corner[-1][1], places=3)

        # Sprawdzamy, czy daleki koniec wyspy (-25, 0) nadal istnieje w wynikowej geometrii
        x_min = min(p[0] for p in res.joined_corner)
        self.assertAlmostEqual(x_min, -25.0, places=1)

    def test_two_curved_lines_corner_fillet_no_spurious_continuation(self):
        # Linia 1: zakrzywiona linia dochodząca do (0, 0)
        pts1 = [
            (20.0, 10.0),
            (15.0, 6.0),
            (10.0, 3.0),
            (5.0, 1.0),
            (0.0, 0.0)
        ]
        click1 = (2.5, 0.5)

        # Linia 2: zakrzywiona linia dochodząca do (0, 0) pod kątem ~90 stopni
        pts2 = [
            (-10.0, 20.0),
            (-6.0, 15.0),
            (-3.0, 10.0),
            (-1.0, 5.0),
            (0.0, 0.0)
        ]
        click2 = (-0.5, 2.5)

        res = fillet_two_lines_2d(
            pts1=pts1,
            click1=click1,
            pts2=pts2,
            click2=click2,
            radius=1.5
        )

        self.assertIsNotNone(res)
        # Żadna z linii nie powinna fałszywie wykryć kontynuacji mimo krzywizn
        self.assertFalse(res.line1_continues)
        self.assertFalse(res.line2_continues)

        # Powstała scalona polilinia (joined_corner)
        self.assertIsNotNone(res.joined_corner)

        # Sprawdzamy, czy dalekie punkty obu linii są zachowane na końcach
        self.assertAlmostEqual(res.joined_corner[0][0], 20.0, places=1)
        self.assertAlmostEqual(res.joined_corner[-1][0], -10.0, places=1)

    def test_same_line_internal_corner(self):
        # Pojedyncza linia z narożnikiem wewnętrznym: (0, 10) -> (0, 0) -> (10, 0)
        pts = [(0.0, 10.0), (0.0, 0.0), (10.0, 0.0)]
        click1 = (0.0, 5.0)
        click2 = (5.0, 0.0)

        res = fillet_two_lines_2d(
            pts1=pts,
            click1=click1,
            pts2=pts,
            click2=click2,
            radius=2.0,
            is_same_line=True
        )

        self.assertIsNotNone(res)
        self.assertIsNotNone(res.joined_corner)
        self.assertAlmostEqual(res.joined_corner[0][0], 0.0)
        self.assertAlmostEqual(res.joined_corner[0][1], 10.0)
        self.assertAlmostEqual(res.joined_corner[-1][0], 10.0)
        self.assertAlmostEqual(res.joined_corner[-1][1], 0.0)


if __name__ == '__main__':
    unittest.main()
