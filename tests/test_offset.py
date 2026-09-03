#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testy jednostkowe dla modułów offsetu wtyczki MSA: CurveMaster.
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

from core.geometry_utils import offset_segment
from core.offset_utils import (
    compute_line_offset,
    compute_polygon_offset,
    extract_rings_as_line
)
from core.layer_modifier import LayerModifier

from qgis.core import (
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes
)


class TestOffsetUtils(unittest.TestCase):

    def test_offset_segment_pure_math(self):
        # Segment poziomy od (0, 0) do (10, 0).
        # Offset +2 powinien dać odcinek na Y=2 (w lewo od kierunku wektora +X)
        p1 = (0.0, 0.0)
        p2 = (10.0, 0.0)
        p1_off, p2_off = offset_segment(p1, p2, 2.0)
        self.assertAlmostEqual(p1_off[0], 0.0)
        self.assertAlmostEqual(p1_off[1], 2.0)
        self.assertAlmostEqual(p2_off[0], 10.0)
        self.assertAlmostEqual(p2_off[1], 2.0)

        # Offset -2 powinien dać odcinek na Y=-2
        p1_neg, p2_neg = offset_segment(p1, p2, -2.0)
        self.assertAlmostEqual(p1_neg[1], -2.0)
        self.assertAlmostEqual(p2_neg[1], -2.0)

    def test_compute_line_offset_left_and_right(self):
        line = QgsGeometry.fromPolylineXY([
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.0),
            QgsPointXY(20.0, 10.0)
        ])

        # Kursor po lewej stronie (Y=3.0)
        cursor_left = QgsPointXY(5.0, 3.0)
        off_left, dist, signed_dist = compute_line_offset(line, cursor_left)
        self.assertFalse(off_left.isEmpty())
        self.assertAlmostEqual(dist, 3.0, places=3)
        self.assertGreater(signed_dist, 0.0)

        # Kursor po prawej stronie (Y=-4.0)
        cursor_right = QgsPointXY(5.0, -4.0)
        off_right, dist_r, signed_dist_r = compute_line_offset(line, cursor_right)
        self.assertFalse(off_right.isEmpty())
        self.assertAlmostEqual(dist_r, 4.0, places=3)
        self.assertLess(signed_dist_r, 0.0)

    def test_compute_line_offset_custom_distance(self):
        line = QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 0.0)])
        cursor_left = QgsPointXY(5.0, 1.0)
        # Wpisujemy zadaną odległość 5.5 m
        off, dist, signed_dist = compute_line_offset(line, cursor_left, custom_distance=5.5)
        self.assertAlmostEqual(dist, 5.5, places=3)
        self.assertAlmostEqual(signed_dist, 5.5, places=3)
        self.assertAlmostEqual(off.distance(QgsGeometry.fromPointXY(QgsPointXY(5.0, 5.5))), 0.0, places=3)

    def test_compute_polygon_offset_outward_and_inward(self):
        poly = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.0),
            QgsPointXY(10.0, 10.0),
            QgsPointXY(0.0, 10.0),
            QgsPointXY(0.0, 0.0)
        ]])

        # Kursor na zewnątrz poligonu w odległości 2 m (np. X=12, Y=5)
        cursor_out = QgsPointXY(12.0, 5.0)
        off_out, dist_out, signed_dist_out = compute_polygon_offset(poly, cursor_out)
        self.assertFalse(off_out.isEmpty())
        self.assertAlmostEqual(dist_out, 2.0, places=3)
        self.assertGreater(signed_dist_out, 0.0)
        # Bufor na zewnątrz o 2 m powinien powiększyć kwadrat 10x10 do 14x14 (powierzchnia 196)
        self.assertAlmostEqual(off_out.area(), 196.0, delta=1.0)

        # Kursor wewnątrz poligonu w odległości 2 m (np. X=2, Y=5)
        cursor_in = QgsPointXY(2.0, 5.0)
        off_in, dist_in, signed_dist_in = compute_polygon_offset(poly, cursor_in)
        self.assertFalse(off_in.isEmpty())
        self.assertAlmostEqual(dist_in, 2.0, places=3)
        self.assertLess(signed_dist_in, 0.0)
        # Bufor do wewnątrz o 2 m powinien pomniejszyć kwadrat 10x10 do 6x6 (powierzchnia 36)
        self.assertAlmostEqual(off_in.area(), 36.0, delta=1.0)

    def test_extract_rings_as_line(self):
        poly = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.0),
            QgsPointXY(10.0, 10.0),
            QgsPointXY(0.0, 0.0)
        ]])
        line_geom = extract_rings_as_line(poly)
        self.assertEqual(line_geom.type(), QgsWkbTypes.LineGeometry)
        self.assertFalse(line_geom.isEmpty())

    def test_layer_modifier_add_feature_with_undo_redo(self):
        layer = QgsVectorLayer('LineString?crs=epsg:2180', 'test_offset_layer', 'memory')
        layer.startEditing()
        self.assertEqual(layer.featureCount(), 0)

        line = QgsGeometry.fromPolylineXY([QgsPointXY(100.0, 100.0), QgsPointXY(200.0, 100.0)])
        feat_id = LayerModifier.add_feature(layer, line, "MSA: Utwórz offset")
        self.assertIsNotNone(feat_id)
        self.assertEqual(layer.featureCount(), 1)

        # Sprawdzenie cofania (Undo)
        layer.undoStack().undo()
        self.assertEqual(layer.featureCount(), 0)

        # Sprawdzenie ponawiania (Redo)
        layer.undoStack().redo()
        self.assertEqual(layer.featureCount(), 1)

    def test_segment_vertex_conversion_no_type_error(self):
        # Test zapobiegający błędowi TypeError: index 0 has type 'QgsPoint' but 'QgsPointXY' is expected
        line = QgsGeometry.fromPolylineXY([QgsPointXY(10.0, 20.0), QgsPointXY(30.0, 40.0), QgsPointXY(50.0, 60.0)])
        v0 = line.vertexAt(0)
        v1 = line.vertexAt(1)
        # vertexAt zwraca QgsPoint, konwersja na QgsPointXY musi działać bez błędu
        p_a = QgsPointXY(v0)
        p_b = QgsPointXY(v1)
        seg_geom = QgsGeometry.fromPolylineXY([p_a, p_b])
        self.assertFalse(seg_geom.isEmpty())
        self.assertEqual(seg_geom.asPolyline()[0], p_a)
        self.assertEqual(seg_geom.asPolyline()[1], p_b)

    def test_overlay_last_distance_and_tab(self):
        from msa_curvemaster.gui.offset_input_overlay import OffsetInputOverlay
        from qgis.PyQt.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        overlay = OffsetInputOverlay()
        submitted = []
        overlay.distanceSubmitted.connect(lambda d: submitted.append(d))

        # Przypadek 1: Pierwsze wpisanie '15' i submit
        overlay.edit.setText("15")
        overlay._on_submit()
        self.assertEqual(submitted, [15.0])
        overlay.set_last_distance(15.0)

        # Przypadek 2: Drugi offset - brak wpisanego tekstu, naciśnięcie Enter/Tab powinno powtórzyć 15.0
        overlay.edit.clear()
        overlay._on_submit()
        self.assertEqual(submitted, [15.0, 15.0])

        # Przypadek 3: Wpisanie nowej wartości '25.5'
        overlay.edit.setText("25.5")
        overlay._on_submit()
        self.assertEqual(submitted, [15.0, 15.0, 25.5])

    def test_offset_candidate_scopes(self):
        from msa_curvemaster.tools.offset_tool import OffsetCandidateScope, OffsetTool
        self.assertEqual(OffsetTool.candidate_scope, OffsetCandidateScope.ALL)
        OffsetTool.candidate_scope = OffsetCandidateScope.LINES_ONLY
        self.assertEqual(OffsetTool.candidate_scope, OffsetCandidateScope.LINES_ONLY)
        OffsetTool.candidate_scope = OffsetCandidateScope.ACTIVE_LAYER
        self.assertEqual(OffsetTool.candidate_scope, OffsetCandidateScope.ACTIVE_LAYER)
        # Przywrócenie domyślnego zakresu
        OffsetTool.candidate_scope = OffsetCandidateScope.ALL

    def test_layer_modifier_adapt_geometry_single_line_from_multi(self):
        layer = QgsVectorLayer('LineString?crs=epsg:2180', 'test_single_line', 'memory')
        layer.startEditing()
        # MultiLineString z 1 częścią
        mls1 = QgsGeometry.fromMultiPolylineXY([[QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 10.0)]])
        feat_id = LayerModifier.add_feature(layer, mls1, "MSA: Multi to Single")
        self.assertIsNotNone(feat_id)
        self.assertTrue(layer.commitChanges(), f"Commit failed: {layer.commitErrors()}")
        self.assertEqual(layer.featureCount(), 1)
        saved_geom = next(layer.getFeatures()).geometry()
        self.assertFalse(saved_geom.isMultipart())
        self.assertEqual(saved_geom.type(), QgsWkbTypes.LineGeometry)

    def test_layer_modifier_adapt_geometry_multi_split_into_single(self):
        layer = QgsVectorLayer('LineString?crs=epsg:2180', 'test_split_lines', 'memory')
        layer.startEditing()
        # MultiLineString z 2 rozłącznymi częściami
        mls2 = QgsGeometry.fromMultiPolylineXY([
            [QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 10.0)],
            [QgsPointXY(20.0, 20.0), QgsPointXY(30.0, 30.0)]
        ])
        feat_id = LayerModifier.add_feature(layer, mls2, "MSA: Multi parts to Single")
        self.assertIsNotNone(feat_id)
        self.assertTrue(layer.commitChanges(), f"Commit failed: {layer.commitErrors()}")
        self.assertEqual(layer.featureCount(), 2)
        for f in layer.getFeatures():
            self.assertFalse(f.geometry().isMultipart())
            self.assertEqual(f.geometry().type(), QgsWkbTypes.LineGeometry)

    def test_layer_modifier_adapt_geometry_drop_z_for_2d_layer(self):
        layer = QgsVectorLayer('LineString?crs=epsg:2180', 'test_drop_z', 'memory')
        layer.startEditing()
        # 3D LineString dodawany do warstwy 2D
        line_z = QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 10.0)])
        line_z.get().addZValue(123.45)
        self.assertTrue(QgsWkbTypes.hasZ(line_z.wkbType()))

        feat_id = LayerModifier.add_feature(layer, line_z, "MSA: Drop Z")
        self.assertIsNotNone(feat_id)
        self.assertTrue(layer.commitChanges(), f"Commit failed: {layer.commitErrors()}")
        saved_geom = next(layer.getFeatures()).geometry()
        self.assertFalse(QgsWkbTypes.hasZ(saved_geom.wkbType()))

    def test_layer_modifier_adapt_geometry_polygon_to_line(self):
        layer = QgsVectorLayer('LineString?crs=epsg:2180', 'test_poly_to_line', 'memory')
        layer.startEditing()
        poly = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.0),
            QgsPointXY(10.0, 10.0),
            QgsPointXY(0.0, 0.0)
        ]])
        feat_id = LayerModifier.add_feature(layer, poly, "MSA: Poly to Line")
        self.assertIsNotNone(feat_id)
        self.assertTrue(layer.commitChanges(), f"Commit failed: {layer.commitErrors()}")
        self.assertEqual(layer.featureCount(), 1)
        saved_geom = next(layer.getFeatures()).geometry()
        self.assertEqual(saved_geom.type(), QgsWkbTypes.LineGeometry)


if __name__ == '__main__':
    unittest.main()
