#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Narzędzie zaokrąglania narożnika/załamania (Corner Fillet)
z obsługą połykania wierzchołków (Multi-vertex) oraz wprowadzania promienia (CAD overlay).
Autor: Mikołaj Sazonov
"""

import math
from typing import Optional, Tuple, List
from qgis.PyQt.QtCore import Qt, QPoint
from qgis.PyQt.QtGui import QColor
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
from ..gui.radius_input_overlay import RadiusInputOverlay
from ..core.geometry_utils import (
    Point2D,
    multi_vertex_fillet,
    fillet_between_segments,
    distance
)
from ..core.layer_modifier import LayerModifier, qgs_points_to_tuples


class CornerFilletTool(BaseCurveTool):
    """
    Narzędzie mapowe do zaokrąglania wierzchołka (narożnika) polilinii lub poligonu łukiem stycznym.
    Wspiera warstwy o dowolnym CRS, połykanie wierzchołków w zasięgu łuku, wpisywanie promienia
    oraz pełną edycję poligonów (w tym wierzchołka początkowego V0).
    """

    STATE_IDLE = 0
    STATE_DRAGGING = 1

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget, iface=None):
        super().__init__(canvas, settings_widget)
        self.iface = iface
        self.state = self.STATE_IDLE

        # Pływający widget CAD do wprowadzania promienia
        self.overlay = RadiusInputOverlay(self.canvas())
        self.overlay.radiusSubmitted.connect(self._on_overlay_radius_submitted)
        self.overlay.cancelled.connect(self._cancel_operation)

        # Gumka do podświetlania połykanych wierzchołków
        self.consumed_band = QgsRubberBand(self.canvas(), QgsWkbTypes.PointGeometry)
        self.consumed_band.setColor(QColor(255, 140, 0, 220))
        self.consumed_band.setIcon(QgsRubberBand.ICON_CIRCLE)
        self.consumed_band.setIconSize(8)

        # Zapamiętane dane modyfikowanego obiektu (współrzędne w CRS warstwy)
        self.target_feature_id: Optional[int] = None
        self.target_part: int = 0
        self.target_ring: int = 0
        self.target_vertex_nr: int = 0
        self.feature_points: List[Point2D] = []
        self.is_closed_ring: bool = False
        self.current_radius: float = 0.0
        self.active_segment_pair: Optional[Tuple[int, int]] = None
        self.active_consumed_indices: List[int] = []

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        layer = self.active_editable_layer()
        if not layer:
            self.clear_preview()
            self.overlay.hide()
            return

        canvas_pt, layer_pt = self.snap_point_layer(e, layer)

        if self.state == self.STATE_IDLE:
            vertex_info = self._find_vertex_near(layer, layer_pt, canvas_pt)
            if vertex_info:
                feat_id, part, ring, v_nr, p_curr, pts_list, is_closed = vertex_info
                p_curr_canvas = self.to_canvas_point(layer, QgsPointXY(p_curr[0], p_curr[1]))
                self.highlight_band.setColor(QColor(0, 150, 255, 220))
                self.highlight_band.reset(QgsWkbTypes.PointGeometry)
                self.highlight_band.addPoint(p_curr_canvas)
            else:
                self.clear_preview()

        elif self.state == self.STATE_DRAGGING:
            if not self.feature_points or self.target_vertex_nr < 0:
                return

            mode = self.settings().sampling_mode()
            step_val = self.settings().step_value()
            drag_p_layer: Point2D = (layer_pt.x(), layer_pt.y())

            fillet_res = multi_vertex_fillet(
                points=self.feature_points,
                vertex_idx=self.target_vertex_nr,
                drag_pt_or_radius=drag_p_layer,
                is_radius=False,
                mode=mode,
                step_value=step_val,
                is_closed=self.is_closed_ring
            )

            if fillet_res:
                t1, arc_points, t2, consumed_indices, eff_r, seg_pair = fillet_res
                self.current_radius = eff_r
                self.active_segment_pair = seg_pair
                self.active_consumed_indices = consumed_indices

                # Podgląd łuku zrzutowany na płótno
                arc_canvas_pts = self.to_canvas_points_list(layer, arc_points)
                self.preview_band.setColor(QColor(235, 40, 40, 230))
                self.preview_band.reset(QgsWkbTypes.LineGeometry)
                for pt in arc_canvas_pts:
                    self.preview_band.addPoint(pt)

                # Podświetlenie połykanych wierzchołków na pomarańczowo na płótnie
                self.consumed_band.reset(QgsWkbTypes.PointGeometry)
                for c_idx in consumed_indices:
                    if 0 <= c_idx < len(self.feature_points):
                        p_c = self.feature_points[c_idx]
                        p_c_canvas = self.to_canvas_point(layer, QgsPointXY(p_c[0], p_c[1]))
                        self.consumed_band.addPoint(p_c_canvas)

                # Aktualizacja pływającego overlay CAD
                self.overlay.set_current_radius(eff_r)
                self.overlay.update_position(e.pos(), self.canvas().rect())
                self.overlay.show()

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.RightButton:
            self._cancel_operation()
            return

        if e.button() != Qt.LeftButton:
            return

        layer = self.active_editable_layer()
        if not layer:
            return

        canvas_pt, layer_pt = self.snap_point_layer(e, layer)

        if self.state == self.STATE_IDLE:
            vertex_info = self._find_vertex_near(layer, layer_pt, canvas_pt)
            if not vertex_info:
                return

            feat_id, part, ring, v_nr, p_curr, pts_list, is_closed = vertex_info
            self.target_feature_id = feat_id
            self.target_part = part
            self.target_ring = ring
            self.target_vertex_nr = v_nr
            self.feature_points = pts_list
            self.is_closed_ring = is_closed

            if self.settings().is_interactive_fillet():
                self.state = self.STATE_DRAGGING
                self.overlay.update_position(e.pos(), self.canvas().rect())
                self.overlay.show()
            else:
                # Tryb zadanego stałego promienia w pasku
                radius = self.settings().fillet_radius()
                self._commit_fillet_with_radius(radius)

        elif self.state == self.STATE_DRAGGING:
            # Zatwierdzenie kliknięciem myszy
            drag_p_layer: Point2D = (layer_pt.x(), layer_pt.y())
            self._commit_fillet_with_point(drag_p_layer)

    def _on_overlay_radius_submitted(self, radius_val: float):
        """Zatwierdzenie promienia wpisanego w pływającym okienku CAD."""
        self._commit_fillet_with_radius(radius_val)

    def _commit_fillet_with_point(self, drag_point_layer: Point2D):
        layer = self.active_editable_layer()
        if layer and self.target_feature_id is not None and self.feature_points:
            mode = self.settings().sampling_mode()
            step_val = self.settings().step_value()

            fillet_res = multi_vertex_fillet(
                points=self.feature_points,
                vertex_idx=self.target_vertex_nr,
                drag_pt_or_radius=drag_point_layer,
                is_radius=False,
                mode=mode,
                step_value=step_val,
                is_closed=self.is_closed_ring
            )

            if fillet_res:
                t1, arc_points, t2, consumed_indices, eff_r, seg_pair = fillet_res
                LayerModifier.apply_vertex_range_replacement(
                    layer=layer,
                    feature_id=self.target_feature_id,
                    part_idx=self.target_part,
                    ring_idx=self.target_ring,
                    consumed_indices=consumed_indices,
                    replacement_pts=arc_points,
                    command_name="MSA: Zaokrąglij łukiem",
                    is_closed=self.is_closed_ring
                )

        self._cancel_operation()

    def _commit_fillet_with_radius(self, radius_val: float):
        layer = self.active_editable_layer()
        if layer and self.target_feature_id is not None and self.feature_points and radius_val > 0:
            mode = self.settings().sampling_mode()
            step_val = self.settings().step_value()

            # Jeśli jesteśmy w trakcie edycji i mamy aktywny kontekst segmentów (np. połączony zakręt)
            if self.active_segment_pair is not None:
                a, b = self.active_segment_pair
                fillet_res = fillet_between_segments(
                    points=self.feature_points,
                    a=a,
                    b=b,
                    radius=radius_val,
                    mode=mode,
                    step_value=step_val,
                    is_closed=self.is_closed_ring
                )
                if fillet_res:
                    t1, arc_points, t2, consumed_indices, eff_r = fillet_res
                    LayerModifier.apply_vertex_range_replacement(
                        layer=layer,
                        feature_id=self.target_feature_id,
                        part_idx=self.target_part,
                        ring_idx=self.target_ring,
                        consumed_indices=consumed_indices,
                        replacement_pts=arc_points,
                        command_name="MSA: Zaokrąglij łukiem",
                        is_closed=self.is_closed_ring
                    )
                    self._cancel_operation()
                    return

            # Fallback dla trybu ze stałym promieniem z paska
            fillet_res_fallback = multi_vertex_fillet(
                points=self.feature_points,
                vertex_idx=self.target_vertex_nr,
                drag_pt_or_radius=radius_val,
                is_radius=True,
                mode=mode,
                step_value=step_val,
                is_closed=self.is_closed_ring
            )

            if fillet_res_fallback:
                t1, arc_points, t2, consumed_indices, eff_r, seg_pair = fillet_res_fallback
                LayerModifier.apply_vertex_range_replacement(
                    layer=layer,
                    feature_id=self.target_feature_id,
                    part_idx=self.target_part,
                    ring_idx=self.target_ring,
                    consumed_indices=consumed_indices,
                    replacement_pts=arc_points,
                    command_name="MSA: Zaokrąglij łukiem",
                    is_closed=self.is_closed_ring
                )
            else:
                if self.iface:
                    self.iface.messageBar().pushWarning(
                        "MSA: CurveMaster",
                        f"Podany promień ({radius_val:.2f} m) jest niemożliwy dla tej geometrii (wykracza poza obiekt)."
                    )

        self._cancel_operation()

    def _cancel_operation(self):
        self.state = self.STATE_IDLE
        self.target_feature_id = None
        self.feature_points = []
        self.is_closed_ring = False
        self.current_radius = 0.0
        self.active_segment_pair = None
        self.active_consumed_indices = []
        self.clear_preview()
        if self.overlay:
            self.overlay.hide()
            self.overlay.edit.clear()

    def clear_preview(self):
        super().clear_preview()
        if self.consumed_band:
            self.consumed_band.reset(QgsWkbTypes.PointGeometry)

    def deactivate(self):
        if self.overlay:
            self.overlay.hide()
        super().deactivate()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel_operation()
            return

        if self.state == self.STATE_DRAGGING:
            # Jeśli wpisano cyfrę lub przecinek/kropkę, przekieruj do overlay
            key_text = e.text()
            if key_text and (key_text.isdigit() or key_text in ('.', ',')):
                self.overlay.activate_with_text(key_text)
                return
            elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.current_radius > 0:
                    self._commit_fillet_with_radius(self.current_radius)
                return
            elif e.key() == Qt.Key_R:
                self.overlay.show()
                self.overlay.edit.setFocus()
                self.overlay.edit.selectAll()
                return

        super().keyPressEvent(e)

    def _find_vertex_near(
        self,
        layer: QgsVectorLayer,
        layer_point: QgsPointXY,
        canvas_point: QgsPointXY
    ) -> Optional[Tuple[int, int, int, int, Point2D, List[Point2D], bool]]:
        """
        Wyszukuje najbliższy wierzchołek na warstwie i zwraca pełną listę punktów części/pierścienia.
        Wspiera transformacje CRS, polilinie oraz poligony (w tym narożnik startowy V0).
        Zwraca: (feat_id, part, ring, vertex_idx, p_curr, points_list, is_closed)
        """
        mupp = self.canvas().mapUnitsPerPixel()
        tol_canvas = mupp * 20.0
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

            closest_pt, closest_v_nr, prev_v_nr, next_v_nr, sqr_dist = geom.closestVertex(layer_point)
            success, v_id = geom.vertexIdFromVertexNr(closest_v_nr)
            if not success:
                continue

            v_curr_geom = geom.vertexAt(closest_v_nr)
            p_curr = (v_curr_geom.x(), v_curr_geom.y())
            p_curr_canvas = self.to_canvas_point(layer, QgsPointXY(p_curr[0], p_curr[1]))

            dist_canvas = math.hypot(canvas_point.x() - p_curr_canvas.x(), canvas_point.y() - p_curr_canvas.y())
            if dist_canvas > tol_canvas or dist_canvas >= best_dist_canvas:
                continue

            # Pobranie punktów całej części/pierścienia
            pts_list: List[Point2D] = []
            is_closed = False
            geom_type = geom.type()
            is_multi = geom.isMultipart()

            if geom_type == QgsWkbTypes.LineGeometry:
                if is_multi:
                    multi_lines = geom.asMultiPolyline()
                    if 0 <= v_id.part < len(multi_lines):
                        pts_list = qgs_points_to_tuples(multi_lines[v_id.part])
                else:
                    pts_list = qgs_points_to_tuples(geom.asPolyline())
                if not pts_list or len(pts_list) < 3:
                    continue

                # Sprawdzenie czy to pętla zamknięta (punkty startowy i końcowy pokrywają się)
                is_closed = (distance(pts_list[0], pts_list[-1]) < max(0.1, tol_canvas))
                if is_closed:
                    if len(pts_list) < 4:
                        continue
                    m = len(pts_list) - 1 if (len(pts_list) > 1 and pts_list[0] == pts_list[-1]) else len(pts_list)
                    target_vertex = v_id.vertex % m
                else:
                    # Skrajne wierzchołki linii otwartej nie mają sąsiedztwa do zaokrąglenia
                    if v_id.vertex <= 0 or v_id.vertex >= len(pts_list) - 1:
                        continue
                    target_vertex = v_id.vertex

            elif geom_type == QgsWkbTypes.PolygonGeometry:
                if is_multi:
                    multi_poly = geom.asMultiPolygon()
                    if 0 <= v_id.part < len(multi_poly):
                        poly = multi_poly[v_id.part]
                        if 0 <= v_id.ring < len(poly):
                            pts_list = qgs_points_to_tuples(poly[v_id.ring])
                else:
                    poly = geom.asPolygon()
                    if 0 <= v_id.ring < len(poly):
                        pts_list = qgs_points_to_tuples(poly[v_id.ring])
                is_closed = True
                if not pts_list or len(pts_list) < 4:
                    continue
                # Dla pierścienia zamkniętego: normalizujemy duplikat końcowy (len-1) na 0
                m = len(pts_list) - 1 if (len(pts_list) > 1 and pts_list[0] == pts_list[-1]) else len(pts_list)
                target_vertex = v_id.vertex % m
            else:
                continue

            if not pts_list:
                continue

            best_dist_canvas = dist_canvas
            best_candidate = (
                feat.id(),
                v_id.part,
                v_id.ring,
                target_vertex,
                p_curr,
                pts_list,
                is_closed
            )

        return best_candidate

