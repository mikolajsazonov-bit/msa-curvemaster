#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Narzędzie przeciągania odcinka w łuk (Bend Segment).
Autor: Mikołaj Sazonov
"""

import math
from typing import Optional, Tuple, List
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QKeySequence
from qgis.gui import (
    QgsMapMouseEvent,
    QgsMapCanvas,
    QgsRubberBand
)
from qgis.core import (
    QgsVectorLayer,
    QgsPointXY,
    QgsGeometry,
    QgsWkbTypes,
    QgsRectangle,
    QgsFeatureRequest,
    QgsVertexId
)
from .base_curve_tool import BaseCurveTool
from ..gui.settings_widget import CurveSettingsWidget
from ..core.geometry_utils import (
    Point2D,
    generate_bend_arc,
    distance
)
from ..core.layer_modifier import LayerModifier


class BendSegmentTool(BaseCurveTool):
    """
    Narzędzie mapowe do wyginania prostego odcinka polilinii/poligonu w zinterpolowany łuk.
    Obsługuje warstwy o dowolnym układzie współrzędnych (CRS) oraz geometrie poligonowe.
    """

    STATE_IDLE = 0
    STATE_DRAGGING = 1

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget):
        super().__init__(canvas, settings_widget)
        self.state = self.STATE_IDLE

        # Zapamiętany aktywny odcinek do modyfikacji (współrzędne w CRS warstwy)
        self.target_feature_id: Optional[int] = None
        self.target_part: int = 0
        self.target_ring: int = 0
        self.target_seg_idx: int = 0
        self.p_start: Optional[Point2D] = None
        self.p_end: Optional[Point2D] = None

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        layer = self.active_editable_layer()
        if not layer:
            self.clear_preview()
            return

        canvas_pt, layer_pt = self.snap_point_layer(e, layer)

        if self.state == self.STATE_IDLE:
            # Szukamy najbliższego odcinka w zasięgu kursora
            seg_info = self._find_segment_near(layer, layer_pt, canvas_pt)
            if seg_info:
                feat_id, part, ring, seg_idx, pt_a, pt_b = seg_info
                # Podświetlenie kandydata na niebiesko (punkty zrzutowane na płótno)
                pt_a_canvas = self.to_canvas_point(layer, QgsPointXY(pt_a[0], pt_a[1]))
                pt_b_canvas = self.to_canvas_point(layer, QgsPointXY(pt_b[0], pt_b[1]))
                self.preview_band.setColor(QColor(0, 140, 255, 200))
                self.preview_band.reset(QgsWkbTypes.LineGeometry)
                self.preview_band.addPoint(pt_a_canvas)
                self.preview_band.addPoint(pt_b_canvas)
            else:
                self.clear_preview()

        elif self.state == self.STATE_DRAGGING:
            if self.p_start is None or self.p_end is None:
                return

            p_mid_layer: Point2D = (layer_pt.x(), layer_pt.y())
            mode = self.settings().sampling_mode()
            step_val = self.settings().step_value()

            arc_points = generate_bend_arc(self.p_start, p_mid_layer, self.p_end, mode, step_val)
            arc_canvas_pts = self.to_canvas_points_list(layer, arc_points)

            self.preview_band.setColor(QColor(235, 40, 40, 230))
            self.preview_band.reset(QgsWkbTypes.LineGeometry)
            for pt in arc_canvas_pts:
                self.preview_band.addPoint(pt)

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.RightButton:
            # Anulowanie operacji prawym przyciskiem myszy
            self._cancel_operation()
            return

        if e.button() != Qt.LeftButton:
            return

        layer = self.active_editable_layer()
        if not layer:
            return

        canvas_pt, layer_pt = self.snap_point_layer(e, layer)

        if self.state == self.STATE_IDLE:
            seg_info = self._find_segment_near(layer, layer_pt, canvas_pt)
            if seg_info:
                feat_id, part, ring, seg_idx, pt_a, pt_b = seg_info
                self.target_feature_id = feat_id
                self.target_part = part
                self.target_ring = ring
                self.target_seg_idx = seg_idx
                self.p_start = pt_a
                self.p_end = pt_b
                self.state = self.STATE_DRAGGING

        elif self.state == self.STATE_DRAGGING:
            # Drugie kliknięcie zatwierdza kształt łuku
            self._commit_bend(layer_pt)

    def _commit_bend(self, final_point_layer: QgsPointXY):
        layer = self.active_editable_layer()
        if layer and self.target_feature_id is not None and self.p_start and self.p_end:
            p_mid_layer: Point2D = (final_point_layer.x(), final_point_layer.y())
            mode = self.settings().sampling_mode()
            step_val = self.settings().step_value()

            arc_points = generate_bend_arc(self.p_start, p_mid_layer, self.p_end, mode, step_val)

            LayerModifier.apply_segment_replacement(
                layer=layer,
                feature_id=self.target_feature_id,
                part_idx=self.target_part,
                ring_idx=self.target_ring,
                seg_idx=self.target_seg_idx,
                replacement_pts=arc_points,
                command_name="MSA: Wygnij odcinek w łuk"
            )

        self._cancel_operation()

    def _cancel_operation(self):
        self.state = self.STATE_IDLE
        self.target_feature_id = None
        self.p_start = None
        self.p_end = None
        self.clear_preview()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel_operation()
        else:
            super().keyPressEvent(e)

    def _find_segment_near(
        self,
        layer: QgsVectorLayer,
        layer_point: QgsPointXY,
        canvas_point: QgsPointXY
    ) -> Optional[Tuple[int, int, int, int, Point2D, Point2D]]:
        """
        Wyszukuje najbliższy odcinek geometrii w warstwie w promieniu tolerancji (ok. 20 pikseli).
        Obsługuje transformację CRS oraz wielokąty (poligony) i polilinie.
        Zwraca: (feature_id, part, ring, seg_idx, p_start, p_end) w układzie CRS warstwy.
        """
        mupp = self._canvas.mapUnitsPerPixel()
        tol_canvas = mupp * 20.0  # 20 px tolerancji wyszukiwania na płótnie
        search_rect_canvas = QgsRectangle(
            canvas_point.x() - tol_canvas,
            canvas_point.y() - tol_canvas,
            canvas_point.x() + tol_canvas,
            canvas_point.y() + tol_canvas
        )
        search_rect_layer = self.to_layer_rect(layer, search_rect_canvas)

        req = QgsFeatureRequest().setFilterRect(search_rect_layer).setFlags(QgsFeatureRequest.ExactIntersect)

        best_dist_canvas = float('inf')
        best_candidate = None

        for feat in layer.getFeatures(req):
            geom = feat.geometry()
            if geom.isEmpty():
                continue

            sqr_dist, min_pt, after_vertex, left_of = geom.closestSegmentWithContext(layer_point)
            start_vertex_nr = after_vertex - 1
            end_vertex_nr = after_vertex

            if start_vertex_nr < 0:
                continue

            success_a, v_id = geom.vertexIdFromVertexNr(start_vertex_nr)
            success_b, _ = geom.vertexIdFromVertexNr(end_vertex_nr)
            if not success_a or not success_b:
                continue

            pt_a_geom = geom.vertexAt(start_vertex_nr)
            pt_b_geom = geom.vertexAt(end_vertex_nr)

            # Rzutowanie punktów odcinka na płótno do dokładnego pomiaru odległości pikselowej
            pt_a_canvas = self.to_canvas_point(layer, QgsPointXY(pt_a_geom.x(), pt_a_geom.y()))
            pt_b_canvas = self.to_canvas_point(layer, QgsPointXY(pt_b_geom.x(), pt_b_geom.y()))

            seg_canvas_geom = QgsGeometry.fromPolylineXY([pt_a_canvas, pt_b_canvas])
            dist_canvas = seg_canvas_geom.distance(QgsGeometry.fromPointXY(canvas_point))

            if dist_canvas <= tol_canvas and dist_canvas < best_dist_canvas:
                best_dist_canvas = dist_canvas
                best_candidate = (
                    feat.id(),
                    v_id.part,
                    v_id.ring,
                    v_id.vertex,
                    (pt_a_geom.x(), pt_a_geom.y()),
                    (pt_b_geom.x(), pt_b_geom.y())
                )

        return best_candidate

