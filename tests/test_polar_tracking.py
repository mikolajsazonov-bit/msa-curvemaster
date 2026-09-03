#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testy jednostkowe dla modułu Polar Trackingu (śledzenia biegunowego CAD).
"""

import math
import os
import sys
import unittest

plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(plugin_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from core.geometry_utils import (
    normalize_angle_deg,
    vector_angle_deg,
    find_polar_snap_angle,
    project_point_on_ray_2d,
    ray_segment_intersection_2d,
    project_point_on_ray_t
)
from core.polar_state import (
    PolarState,
    PolarAngleMeasurement,
    POLAR_INCREMENT_PRESETS,
    format_preset_label
)
from core.layer_modifier import LayerModifier

from qgis.core import (
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes
)


class TestPolarTracking(unittest.TestCase):

    def test_normalize_angle_deg(self):
        self.assertAlmostEqual(normalize_angle_deg(0.0), 0.0)
        self.assertAlmostEqual(normalize_angle_deg(360.0), 0.0)
        self.assertAlmostEqual(normalize_angle_deg(450.0), 90.0)
        self.assertAlmostEqual(normalize_angle_deg(-90.0), 270.0)
        self.assertAlmostEqual(normalize_angle_deg(-360.0), 0.0)

    def test_vector_angle_deg(self):
        # Wschód (+X)
        self.assertAlmostEqual(vector_angle_deg((0, 0), (10, 0)), 0.0, places=4)
        # Północ (+Y)
        self.assertAlmostEqual(vector_angle_deg((0, 0), (0, 10)), 90.0, places=4)
        # Zachód (-X)
        self.assertAlmostEqual(vector_angle_deg((0, 0), (-10, 0)), 180.0, places=4)
        # Południe (-Y)
        self.assertAlmostEqual(vector_angle_deg((0, 0), (0, -10)), 270.0, places=4)
        # 45 stopni
        self.assertAlmostEqual(vector_angle_deg((0, 0), (10, 10)), 45.0, places=4)
        # 135 stopni
        self.assertAlmostEqual(vector_angle_deg((0, 0), (-10, 10)), 135.0, places=4)

    def test_find_polar_snap_angle_absolute(self):
        # Krok 15°, kursor na 14.2° -> snapuje do 15.0°
        res = find_polar_snap_angle(current_angle_deg=14.2, base_angle_deg=0.0, increment_deg=15.0, tolerance_deg=4.0)
        self.assertIsNotNone(res)
        map_angle, rel_angle = res
        self.assertAlmostEqual(map_angle, 15.0, places=3)
        self.assertAlmostEqual(rel_angle, 15.0, places=3)

        # Kursor na 20.0° przy kroku 15° (odchyłka 5° > tolerancja 4°) -> brak snapu
        res_none = find_polar_snap_angle(current_angle_deg=20.0, base_angle_deg=0.0, increment_deg=15.0, tolerance_deg=4.0)
        self.assertIsNone(res_none)

        # Blisko 0° (np. 358.5° -> snap do 0.0°)
        res_zero = find_polar_snap_angle(current_angle_deg=358.5, base_angle_deg=0.0, increment_deg=15.0, tolerance_deg=4.0)
        self.assertIsNotNone(res_zero)
        map_angle_zero, _ = res_zero
        self.assertAlmostEqual(map_angle_zero, 0.0, places=3)

    def test_find_polar_snap_angle_relative(self):
        # Krawędź początkowa pod kątem 33.5° (base_angle = 33.5°)
        # Szukamy kąta prostego 90° (czyli w terenie 123.5°)
        # Kursor w pobliżu 124.0°
        res = find_polar_snap_angle(
            current_angle_deg=124.0,
            base_angle_deg=33.5,
            increment_deg=15.0,  # 90 jest wielokrotnością 15
            tolerance_deg=4.0
        )
        self.assertIsNotNone(res)
        map_angle, rel_angle = res
        self.assertAlmostEqual(rel_angle, 90.0, places=3)
        self.assertAlmostEqual(map_angle, 123.5, places=3)

        # Równoległa w drugą stronę (180° względem bazy -> 213.5°)
        res_parallel = find_polar_snap_angle(
            current_angle_deg=214.2,
            base_angle_deg=33.5,
            increment_deg=15.0,
            tolerance_deg=4.0
        )
        self.assertIsNotNone(res_parallel)
        m_ang, r_ang = res_parallel
        self.assertAlmostEqual(r_ang, 180.0, places=3)
        self.assertAlmostEqual(m_ang, 213.5, places=3)

    def test_find_polar_snap_angle_additional_angles(self):
        # Kąt dodatkowy 147.0° (niebędący wielokrotnością 15°)
        add_angles = [147.0]
        res = find_polar_snap_angle(
            current_angle_deg=146.2,
            base_angle_deg=0.0,
            increment_deg=15.0,
            additional_angles=add_angles,
            tolerance_deg=4.0
        )
        self.assertIsNotNone(res)
        map_angle, rel_angle = res
        self.assertAlmostEqual(map_angle, 147.0, places=3)
        self.assertAlmostEqual(rel_angle, 147.0, places=3)

    def test_project_point_on_ray_2d(self):
        origin = (100.0, 200.0)
        # Odmierz 50 m pod kątem 0° (na wschód)
        p_east = project_point_on_ray_2d(origin, 50.0, 0.0)
        self.assertAlmostEqual(p_east[0], 150.0, places=3)
        self.assertAlmostEqual(p_east[1], 200.0, places=3)

        # Odmierz 50 m pod kątem 90° (na północ)
        p_north = project_point_on_ray_2d(origin, 50.0, 90.0)
        self.assertAlmostEqual(p_north[0], 100.0, places=3)
        self.assertAlmostEqual(p_north[1], 250.0, places=3)

    def test_polar_state_and_presets(self):
        state = PolarState.instance()
        self.assertIn(15.0, POLAR_INCREMENT_PRESETS)
        self.assertIn(90.0, POLAR_INCREMENT_PRESETS)

        state.increment_angle = 30.0
        self.assertEqual(state.increment_angle, 30.0)

        state.measurement_mode = PolarAngleMeasurement.RELATIVE
        self.assertEqual(state.measurement_mode, PolarAngleMeasurement.RELATIVE)

        state.add_additional_angle(147.0)
        self.assertIn(147.0, state.additional_angles)
        state.additional_angles_enabled = True
        self.assertIn(147.0, state.get_active_additional_angles())

        state.remove_additional_angle(147.0)
        self.assertNotIn(147.0, state.additional_angles)

        label_15 = format_preset_label(15.0)
        self.assertIn("15", label_15)

    def test_create_line_and_polygon_features(self):
        # 1. Warstwa liniowa
        line_layer = QgsVectorLayer('LineString?crs=epsg:2180', 'test_polar_lines', 'memory')
        line_layer.startEditing()

        pts = [QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10)]
        line_geom = QgsGeometry.fromPolylineXY(pts)
        f_line = LayerModifier.add_feature(line_layer, line_geom, "MSA: Rysuj linię")
        self.assertIsNotNone(f_line)
        self.assertEqual(line_layer.featureCount(), 1)

        # Cofnij (Undo)
        line_layer.undoStack().undo()
        self.assertEqual(line_layer.featureCount(), 0)

        # 2. Warstwa poligonowa
        poly_layer = QgsVectorLayer('Polygon?crs=epsg:2180', 'test_polar_polys', 'memory')
        poly_layer.startEditing()

        poly_pts = [QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 0)]
        poly_geom = QgsGeometry.fromPolygonXY([poly_pts])
        f_poly = LayerModifier.add_feature(poly_layer, poly_geom, "MSA: Rysuj poligon")
        self.assertIsNotNone(f_poly)
        self.assertEqual(poly_layer.featureCount(), 1)

    def test_polar_background_manager_enables_cad(self):
        from qgis.PyQt.QtWidgets import QApplication
        from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas, QgsMapToolCapture
        from core.polar_background_manager import PolarBackgroundManager

        app = QApplication.instance() or QApplication([])
        canvas = QgsMapCanvas()
        cad = QgsAdvancedDigitizingDockWidget(canvas)
        layer = QgsVectorLayer('LineString?crs=epsg:2180', 'test_cad_layer', 'memory')
        layer.startEditing()
        canvas.setCurrentLayer(layer)

        class MockIface:
            def __init__(self, c, cd):
                self._c = c
                self._cd = cd
            def mapCanvas(self): return self._c
            def cadDockWidget(self): return self._cd

        iface = MockIface(canvas, cad)
        mgr = PolarBackgroundManager(iface)

        # Narzędzie CAD (np. Zmień kształt lub Dodaj obiekt)
        tool = QgsMapToolCapture(canvas, cad, QgsMapToolCapture.CaptureLine)
        canvas.setMapTool(tool)

        state = PolarState.instance()
        state.enabled = True
        state.increment_angle = 15.0
        mgr.sync_with_qgis_cad()

        self.assertTrue(cad.cadEnabled())
        self.assertTrue(cad.enableAction().isChecked())
        self.assertTrue(cad.commonAngleConstraint())

        # Wyłączenie
        state.enabled = False
        mgr.sync_with_qgis_cad()
        self.assertFalse(cad.enableAction().isChecked())

    def test_polar_snapping_menu_creation(self):
        from qgis.PyQt.QtWidgets import QApplication
        from qgis.gui import QgsMapCanvas
        from msa_curvemaster.gui.settings_widget import CurveSettingsWidget
        from msa_curvemaster.tools.polar_digitize_tool import PolarDigitizeTool

        app = QApplication.instance() or QApplication([])
        canvas = QgsMapCanvas()
        settings = CurveSettingsWidget()
        tool = PolarDigitizeTool(canvas, settings)

        menu = tool.create_dropdown_menu()
        self.assertIsNotNone(menu)

        menu_titles = [m.title() for m in menu.findChildren(type(menu))]
        self.assertIn("Przyciąganie (Snapping)", menu_titles)

    def test_ray_segment_intersection_math(self):
        # 1. Prostopadłe przecięcie: promień na północ (90°), pozioma linia na y=25
        inter = ray_segment_intersection_2d((10.0, 0.0), 90.0, (-10.0, 25.0), (30.0, 25.0))
        self.assertIsNotNone(inter)
        t, (ix, iy) = inter
        self.assertAlmostEqual(t, 25.0, places=4)
        self.assertAlmostEqual(ix, 10.0, places=4)
        self.assertAlmostEqual(iy, 25.0, places=4)

        # 2. Promień równoległy (brak przecięcia)
        parallel_inter = ray_segment_intersection_2d((0.0, 0.0), 0.0, (-10.0, 25.0), (30.0, 25.0))
        self.assertIsNone(parallel_inter)

        # 3. Odcinek za plecami promienia (t < 0)
        behind_inter = ray_segment_intersection_2d((10.0, 0.0), 90.0, (-10.0, -25.0), (30.0, -25.0))
        self.assertIsNone(behind_inter)

    def test_project_point_on_ray_math(self):
        # Wierzchołek (20, 1) przy promieniu wzdłuż osi X (0°)
        t, perp, (px, py) = project_point_on_ray_t((0.0, 0.0), 0.0, (20.0, 1.0))
        self.assertAlmostEqual(t, 20.0, places=4)
        self.assertAlmostEqual(perp, 1.0, places=4)
        self.assertAlmostEqual(px, 20.0, places=4)
        self.assertAlmostEqual(py, 0.0, places=4)


if __name__ == '__main__':
    unittest.main()
