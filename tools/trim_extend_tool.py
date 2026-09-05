#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Narzędzie Trim / Extend (Utnij / Wydłuż).
Odpowiednik funkcji CAD w AutoCADzie:
- Zwykłe kliknięcie (Left Click): Wydłużenie linii (Extend) do najbliższego obiektu.
- Kliknięcie z Shiftem (Shift + Click): Przycięcie (Trim) wskazanego fragmentu linii.
Autor: Mikołaj Sazonov
"""

import math
from enum import Enum
from typing import Optional, Tuple, List
from qgis.PyQt.QtCore import Qt, QPoint, QEvent
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QActionGroup,
    QWidgetAction,
    QMenu,
    QLabel,
    QApplication
)
from qgis.gui import (
    QgsMapMouseEvent,
    QgsMapCanvas,
    QgsRubberBand,
    QgsSnapIndicator
)
from qgis.core import (
    QgsVectorLayer,
    QgsPointXY,
    QgsGeometry,
    QgsWkbTypes,
    QgsRectangle,
    QgsFeature,
    QgsFeatureRequest,
    QgsCoordinateTransform,
    QgsProject,
    Qgis,
    QgsMessageLog
)
from .base_curve_tool import BaseCurveTool
from ..gui.settings_widget import CurveSettingsWidget
from ..core.geometry_utils import (
    Point2D,
    distance,
    ray_polyline_intersection,
    trim_polyline_with_boundaries
)
from ..core.layer_modifier import LayerModifier, qgs_points_to_tuples, tuples_to_qgs_points
from ..core.offset_utils import extract_rings_as_line
try:
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.i18n import tr


class TrimExtendCandidateScope(Enum):
    """Zakres wyszukiwania krawędzi granicznych / tnących."""
    ALL = "all"                 # Wszystkie obiekty (linie i poligony ze wszystkich warstw) [Domyślne]
    LINES_ONLY = "lines_only"   # Tylko obiekty liniowe (ze wszystkich warstw)
    ACTIVE_LAYER = "active"     # Tylko z aktualnej (edytowanej) warstwy


class TrimExtendTool(BaseCurveTool):
    """
    Narzędzie mapowe do przycinania (Trim) i wydłużania (Extend) linii w edytowalnej warstwie QGIS.
    """

    candidate_scope: TrimExtendCandidateScope = TrimExtendCandidateScope.ALL

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget, iface=None):
        super().__init__(canvas, settings_widget)
        self.iface = iface

        # Gumka do podświetlenia obiektu bazowego
        self.base_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.base_band.setColor(QColor(0, 140, 255, 180))
        self.base_band.setWidth(2)

        # Gumka do podglądu operacji (zielona dla extend, czerwona dla trim)
        self.action_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.action_band.setColor(QColor(25, 135, 84, 230))
        self.action_band.setWidth(3)

        # Wskaźnik przyciągania QGIS (Snapping)
        self.snap_indicator = QgsSnapIndicator(self.canvas())

        # Ostatnia pozycja kursora dla natychmiastowej aktualizacji przy wciśnięciu Shift
        self._last_canvas_pt: Optional[QgsPointXY] = None
        self._last_pixel_pos: Optional[QPoint] = None

        # Zapamiętany stan bieżącej operacji hover
        self._hover_feature_id: Optional[int] = None
        self._hover_part_idx: int = 0
        self._hover_line_pts: List[Point2D] = []
        self._hover_extend_pt: Optional[Point2D] = None
        self._hover_extend_dist: float = 0.0
        self._hover_extend_end_idx: int = 0  # 0 dla początku, -1 dla końca
        self._hover_trim_piece: Optional[List[Point2D]] = None
        self._hover_remaining_pieces: Optional[List[List[Point2D]]] = None

    def activate(self):
        super().activate()
        self.canvas().setFocus()

    def deactivate(self):
        self.clear_preview()
        self._last_canvas_pt = None
        self._last_pixel_pos = None
        if hasattr(self, 'snap_indicator') and self.snap_indicator:
            self.snap_indicator.setVisible(False)
        super().deactivate()

    def clear_preview(self):
        super().clear_preview()
        if hasattr(self, 'base_band') and self.base_band:
            self.base_band.reset(QgsWkbTypes.LineGeometry)
        if hasattr(self, 'action_band') and self.action_band:
            self.action_band.reset(QgsWkbTypes.LineGeometry)
        self._hover_feature_id = None
        self._hover_line_pts = []
        self._hover_extend_pt = None
        self._hover_trim_piece = None
        self._hover_remaining_pieces = None

    def create_dropdown_menu(self, parent=None) -> QMenu:
        """Menu wyboru zakresu krawędzi granicznych/tnących."""
        menu = QMenu(parent or self.canvas())
        menu.setTitle(tr("Candidate Scope for Trim / Extend", "Zakres krawędzi Trim / Extend"))

        lbl_header = QLabel(tr("  Boundary / Cutting edges:", "  Krawędzie graniczne / tnące:"))
        lbl_header.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
        act_header = QWidgetAction(menu)
        act_header.setDefaultWidget(lbl_header)
        menu.addAction(act_header)

        group = QActionGroup(menu)
        group.setExclusive(True)

        options = [
            (
                tr("All objects (lines and polygons)", "Wszystkie obiekty (linie i poligony)"),
                TrimExtendCandidateScope.ALL,
                tr("Use lines, polylines, and polygon boundaries from all visible layers as boundaries",
                   "Używaj linii i granic poligonów ze wszystkich widocznych warstw jako krawędzi")
            ),
            (
                tr("Line features only", "Tylko obiekty liniowe"),
                TrimExtendCandidateScope.LINES_ONLY,
                tr("Restrict boundaries to lines and polylines across all layers",
                   "Ogranicz krawędzie graniczne tylko do obiektów liniowych ze wszystkich warstw")
            ),
            (
                tr("Active editable layer only", "Tylko z aktualnej warstwy"),
                TrimExtendCandidateScope.ACTIVE_LAYER,
                tr("Use objects only from the currently edited layer as boundaries",
                   "Używaj obiektów wyłącznie z aktualnie edytowanej warstwy jako krawędzi")
            ),
        ]

        action_scope_map = []
        for label, scope, tooltip in options:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setToolTip(tooltip)
            act.setChecked(TrimExtendTool.candidate_scope == scope)
            group.addAction(act)

            def make_handler(s=scope):
                return lambda: self._set_candidate_scope(s)
            act.triggered.connect(make_handler(scope))
            action_scope_map.append((act, scope))

        def on_about_to_show():
            for a, s in action_scope_map:
                a.setChecked(TrimExtendTool.candidate_scope == s)

        menu.aboutToShow.connect(on_about_to_show)
        return menu

    def _set_candidate_scope(self, scope: TrimExtendCandidateScope):
        TrimExtendTool.candidate_scope = scope
        scope_names = {
            TrimExtendCandidateScope.ALL: tr("All objects (lines and polygons)", "Wszystkie obiekty (linie i poligony)"),
            TrimExtendCandidateScope.LINES_ONLY: tr("Line features only", "Tylko obiekty liniowe"),
            TrimExtendCandidateScope.ACTIVE_LAYER: tr("Active editable layer only", "Tylko aktualna edytowana warstwa")
        }
        name = scope_names.get(scope, "")
        self._set_status_tip(tr(f"MSA Trim/Extend: Scope set to: {name}", f"MSA Trim/Extend: Ustawiono zakres krawędzi: {name}"))

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        self._last_canvas_pt = QgsPointXY(e.mapPoint())
        self._last_pixel_pos = QPoint(e.pos())
        is_shift = bool(e.modifiers() & Qt.ShiftModifier)
        self._update_hover_preview(self._last_canvas_pt, self._last_pixel_pos, is_shift)

    def _update_hover_preview(self, canvas_pt: QgsPointXY, pixel_pos: QPoint, is_shift: bool):
        active_layer = self.active_editable_layer()
        if not active_layer or active_layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.clear_preview()
            self._set_status_tip(tr(
                "MSA Trim/Extend: Select an editable line layer.",
                "MSA Trim/Extend: Wybierz edytowalną warstwę liniową."
            ))
            return

        layer_pt = self.to_layer_point(active_layer, canvas_pt)

        # Sprawdzenie przyciągania QGIS
        match = self.canvas().snappingUtils().snapToMap(pixel_pos)
        if match.isValid():
            self.snap_indicator.setMatch(match)
            self.snap_indicator.setVisible(True)
        else:
            self.snap_indicator.setVisible(False)

        # Wyszukaj linię w aktywnej warstwie pod kursorem
        target_info = self._find_target_line_near(active_layer, canvas_pt, layer_pt)
        if not target_info:
            self.clear_preview()
            hint = tr("[Shift = Trim]", "[Shift = Przytnij (Trim)]") if not is_shift else tr("[Release Shift = Extend]", "[Zwolnij Shift = Wydłuż (Extend)]")
            self._set_status_tip(f"MSA Trim/Extend: {tr('Hover over a line in the active layer.', 'Najedź na linię w aktywnej warstwie.')} {hint}")
            return

        feat_id, part_idx, line_pts, closest_seg_idx = target_info
        self._hover_feature_id = feat_id
        self._hover_part_idx = part_idx
        self._hover_line_pts = line_pts

        # Podświetl linię bazową na niebiesko
        line_canvas_pts = self.to_canvas_points_list(active_layer, line_pts)
        self.base_band.reset(QgsWkbTypes.LineGeometry)
        for pt in line_canvas_pts:
            self.base_band.addPoint(pt)

        # Zbierz wszystkie krawędzie tnące/graniczne
        boundaries = self._collect_boundary_lines(active_layer, feat_id)

        if is_shift:
            # TRYB TRIM (Utnij)
            self._handle_trim_hover(active_layer, line_pts, boundaries, (layer_pt.x(), layer_pt.y()))
        else:
            # TRYB EXTEND (Wydłuż)
            self._handle_extend_hover(active_layer, line_pts, closest_seg_idx, boundaries, (layer_pt.x(), layer_pt.y()))

    def _handle_extend_hover(
        self,
        layer: QgsVectorLayer,
        line_pts: List[Point2D],
        closest_seg_idx: int,
        boundaries: List[List[Point2D]],
        cursor_layer_pt: Point2D
    ):
        """Podgląd operacji Extend (wydłużenia do najbliższej krawędzi)."""
        self._hover_trim_piece = None
        self._hover_remaining_pieces = None

        if len(line_pts) < 2 or not boundaries:
            self.action_band.reset(QgsWkbTypes.LineGeometry)
            self._hover_extend_pt = None
            self._set_status_tip(tr("MSA Extend: No boundary edges found in scope.", "MSA Extend: Brak krawędzi granicznych w wybranym zakresie."))
            return

        # Określ, który koniec linii jest bliżej kursora
        d_start = distance(cursor_layer_pt, line_pts[0])
        d_end = distance(cursor_layer_pt, line_pts[-1])

        if d_start < d_end:
            # Wydłużenie od początku (vertex 0) w kierunku vertex 1 -> vertex 0
            origin = line_pts[0]
            dx = line_pts[0][0] - line_pts[1][0]
            dy = line_pts[0][1] - line_pts[1][1]
            end_idx = 0
        else:
            # Wydłużenie od końca (vertex n-1) w kierunku vertex n-2 -> vertex n-1
            origin = line_pts[-1]
            dx = line_pts[-1][0] - line_pts[-2][0]
            dy = line_pts[-1][1] - line_pts[-2][1]
            end_idx = -1

        ray_dir = (dx, dy)
        best_t = float('inf')
        best_ipt = None

        for b_line in boundaries:
            res = ray_polyline_intersection(origin, ray_dir, b_line, min_t=1e-3)
            if res is not None:
                t, ipt = res
                if t < best_t:
                    best_t = t
                    best_ipt = ipt

        if best_ipt is not None and best_t < float('inf'):
            self._hover_extend_pt = best_ipt
            self._hover_extend_dist = best_t
            self._hover_extend_end_idx = end_idx

            # Pokaż podgląd przedłużenia na zielono
            p_orig_canvas = self.to_canvas_point(layer, QgsPointXY(origin[0], origin[1]))
            p_ext_canvas = self.to_canvas_point(layer, QgsPointXY(best_ipt[0], best_ipt[1]))

            self.action_band.setColor(QColor(25, 135, 84, 230)) # Zielony
            self.action_band.setWidth(3)
            self.action_band.reset(QgsWkbTypes.LineGeometry)
            self.action_band.addPoint(p_orig_canvas)
            self.action_band.addPoint(p_ext_canvas)

            self._set_status_tip(tr(
                f"MSA Extend: Click to extend line by {best_t:.2f} m. [Shift = Trim]",
                f"MSA Extend: Kliknij, aby wydłużyć linię o {best_t:.2f} m do obiektu. [Shift = Przytnij (Trim)]"
            ))
        else:
            self.action_band.reset(QgsWkbTypes.LineGeometry)
            self._hover_extend_pt = None
            self._set_status_tip(tr(
                "MSA Extend: No boundary edge intersects the extension line. [Shift = Trim]",
                "MSA Extend: Brak obiektu granicznego na drodze przedłużenia linii. [Shift = Przytnij (Trim)]"
            ))

    def _handle_trim_hover(
        self,
        layer: QgsVectorLayer,
        line_pts: List[Point2D],
        boundaries: List[List[Point2D]],
        cursor_layer_pt: Point2D
    ):
        """Podgląd operacji Trim (przycięcia wskazanego fragmentu na czerwono)."""
        self._hover_extend_pt = None

        res = trim_polyline_with_boundaries(line_pts, boundaries, cursor_layer_pt)
        if res is not None:
            trimmed_piece, remaining_pieces = res
            self._hover_trim_piece = trimmed_piece
            self._hover_remaining_pieces = remaining_pieces

            # Pokaż usuwany fragment na jaskrawo czerwono
            self.action_band.setColor(QColor(220, 53, 69, 240)) # Czerwony
            self.action_band.setWidth(4)
            self.action_band.reset(QgsWkbTypes.LineGeometry)
            canvas_pts = self.to_canvas_points_list(layer, trimmed_piece)
            for pt in canvas_pts:
                self.action_band.addPoint(pt)

            self._set_status_tip(tr(
                "MSA Trim: Click with Shift to cut this segment. [Release Shift = Extend]",
                "MSA Trim: Kliknij z Shiftem, aby usunąć ten fragment linii. [Zwolnij Shift = Wydłuż (Extend)]"
            ))
        else:
            self.action_band.reset(QgsWkbTypes.LineGeometry)
            self._hover_trim_piece = None
            self._hover_remaining_pieces = None
            self._set_status_tip(tr(
                "MSA Trim: Line has no intersections with cutting edges. [Release Shift = Extend]",
                "MSA Trim: Linia nie przecina się z żadną krawędzią tnącą. [Zwolnij Shift = Wydłuż (Extend)]"
            ))

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.RightButton:
            self.clear_preview()
            return

        if e.button() != Qt.LeftButton:
            return

        active_layer = self.active_editable_layer()
        if not active_layer or self._hover_feature_id is None:
            return

        is_shift = bool(e.modifiers() & Qt.ShiftModifier)

        if is_shift:
            # WYKONANIE PRZYCIĘCIA (TRIM)
            self._commit_trim(active_layer)
        else:
            # WYKONANIE WYDŁUŻENIA (EXTEND)
            self._commit_extend(active_layer)

    def _commit_extend(self, layer: QgsVectorLayer):
        """Zatwierdzenie operacji Extend."""
        if self._hover_feature_id is None or not self._hover_extend_pt or not self._hover_line_pts:
            return

        feat = layer.getFeature(self._hover_feature_id)
        if not feat.isValid():
            return

        new_pts = list(self._hover_line_pts)
        if self._hover_extend_end_idx == 0:
            new_pts.insert(0, self._hover_extend_pt)
        else:
            new_pts.append(self._hover_extend_pt)

        # Uaktualnij geometrię w obiekcie
        orig_geom = feat.geometry()
        new_geom = None

        if orig_geom.isMultipart():
            multi_lines = orig_geom.asMultiPolyline()
            if 0 <= self._hover_part_idx < len(multi_lines):
                multi_lines[self._hover_part_idx] = tuples_to_qgs_points(new_pts)
                new_geom = QgsGeometry.fromMultiPolylineXY(multi_lines)
        else:
            new_geom = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(new_pts))

        if new_geom and not new_geom.isEmpty():
            adapted = LayerModifier.adapt_geometry_to_layer(layer, new_geom)
            if adapted:
                layer.beginEditCommand(tr("MSA: Extend line", "MSA: Wydłuż linię (Extend)"))
                success = layer.changeGeometry(self._hover_feature_id, adapted[0])
                if success:
                    layer.endEditCommand()
                    layer.triggerRepaint()
                    if self.iface:
                        self.iface.messageBar().pushInfo(
                            "MSA: CurveMaster",
                            tr(f"Line extended by {self._hover_extend_dist:.2f} m.",
                               f"Wydłużono linię o {self._hover_extend_dist:.2f} m.")
                        )
                else:
                    layer.destroyEditCommand()

        self.clear_preview()
        if self._last_canvas_pt and self._last_pixel_pos:
            is_shift = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
            self._update_hover_preview(self._last_canvas_pt, self._last_pixel_pos, is_shift)

    def _commit_trim(self, layer: QgsVectorLayer):
        """Zatwierdzenie operacji Trim."""
        if self._hover_feature_id is None or not self._hover_remaining_pieces:
            return

        feat = layer.getFeature(self._hover_feature_id)
        if not feat.isValid():
            return

        rem_pieces = self._hover_remaining_pieces

        layer.beginEditCommand(tr("MSA: Trim line", "MSA: Przytnij linię (Trim)"))

        if len(rem_pieces) == 1:
            # Tylko jeden fragment pozostał (skrócenie z jednego końca)
            new_geom = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(rem_pieces[0]))
            adapted = LayerModifier.adapt_geometry_to_layer(layer, new_geom)
            if adapted:
                layer.changeGeometry(self._hover_feature_id, adapted[0])
        elif len(rem_pieces) >= 2:
            # Rozcięcie na co najmniej 2 części
            layer_is_multi = QgsWkbTypes.isMultiType(layer.wkbType())
            if layer_is_multi:
                multi_lines = [tuples_to_qgs_points(p) for p in rem_pieces]
                new_geom = QgsGeometry.fromMultiPolylineXY(multi_lines)
                adapted = LayerModifier.adapt_geometry_to_layer(layer, new_geom)
                if adapted:
                    layer.changeGeometry(self._hover_feature_id, adapted[0])
            else:
                # Warstwa jednoczęściowa: pierwsza część w starym obiekcie, kolejne jako nowe obiekty
                g0 = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(rem_pieces[0]))
                ad0 = LayerModifier.adapt_geometry_to_layer(layer, g0)
                if ad0:
                    layer.changeGeometry(self._hover_feature_id, ad0[0])

                for p in rem_pieces[1:]:
                    gi = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(p))
                    adi = LayerModifier.adapt_geometry_to_layer(layer, gi)
                    if adi:
                        new_f = QgsFeature(layer.fields())
                        # Kopiuj atrybuty z oryginalnego obiektu bez unikalnego ID (fid)
                        new_f.setAttributes(LayerModifier.copy_attributes_for_new_feature(layer, feat))
                        new_f.setGeometry(adi[0])
                        layer.addFeature(new_f)

        layer.endEditCommand()
        layer.triggerRepaint()
        if self.iface:
            self.iface.messageBar().pushInfo(
                "MSA: CurveMaster",
                tr("Line segment trimmed.", "Przycięto fragment linii.")
            )

        self.clear_preview()
        if self._last_canvas_pt and self._last_pixel_pos:
            is_shift = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
            self._update_hover_preview(self._last_canvas_pt, self._last_pixel_pos, is_shift)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Shift and self._last_canvas_pt and self._last_pixel_pos:
            self._update_hover_preview(self._last_canvas_pt, self._last_pixel_pos, is_shift=True)
            return
        elif e.key() == Qt.Key_Escape:
            self.clear_preview()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Shift and self._last_canvas_pt and self._last_pixel_pos:
            self._update_hover_preview(self._last_canvas_pt, self._last_pixel_pos, is_shift=False)
            return
        super().keyReleaseEvent(e)

    def _find_target_line_near(
        self,
        layer: QgsVectorLayer,
        canvas_pt: QgsPointXY,
        layer_pt: QgsPointXY
    ) -> Optional[Tuple[int, int, List[Point2D], int]]:
        """Wyszukuje najbliższą linię w aktywnej warstwie pod kursorem."""
        mupp = self.canvas().mapUnitsPerPixel()
        tol_canvas = mupp * 20.0
        search_rect_canvas = QgsRectangle(
            canvas_pt.x() - tol_canvas,
            canvas_pt.y() - tol_canvas,
            canvas_pt.x() + tol_canvas,
            canvas_pt.y() + tol_canvas
        )
        search_rect_layer = self.to_layer_rect(layer, search_rect_canvas)
        req = QgsFeatureRequest().setFilterRect(search_rect_layer).setFlags(QgsFeatureRequest.ExactIntersect)

        best_dist = float('inf')
        best_match = None

        for feat in layer.getFeatures(req):
            geom = feat.geometry()
            if geom.isEmpty() or geom.type() != QgsWkbTypes.LineGeometry:
                continue

            sqr_d, min_pt, after_v, left_of = geom.closestSegmentWithContext(layer_pt)
            min_pt_canvas = self.to_canvas_point(layer, min_pt)
            d_canvas = math.hypot(canvas_pt.x() - min_pt_canvas.x(), canvas_pt.y() - min_pt_canvas.y())

            if d_canvas <= tol_canvas and d_canvas < best_dist:
                best_dist = d_canvas
                # Wyciągnij punkty właściwej części
                pts_list = []
                part_idx = 0
                if geom.isMultipart():
                    multi_lines = geom.asMultiPolyline()
                    success, v_id = geom.vertexIdFromVertexNr(after_v)
                    part = v_id.part if success and 0 <= v_id.part < len(multi_lines) else 0
                    pts_list = qgs_points_to_tuples(multi_lines[part])
                    part_idx = part
                else:
                    pts_list = qgs_points_to_tuples(geom.asPolyline())

                if len(pts_list) >= 2:
                    seg_idx = max(0, after_v - 1)
                    best_match = (feat.id(), part_idx, pts_list, seg_idx)

        return best_match

    def _collect_boundary_lines(self, active_layer: QgsVectorLayer, exclude_feat_id: int) -> List[List[Point2D]]:
        """Zbiera krawędzie graniczne/tnące ze wszystkich warstw zgodnie z candidate_scope."""
        target_crs = active_layer.crs()
        mupp = self.canvas().mapUnitsPerPixel()
        canvas_extent = self.canvas().extent()

        layers_to_check: List[QgsVectorLayer] = [active_layer]

        if TrimExtendTool.candidate_scope != TrimExtendCandidateScope.ACTIVE_LAYER:
            for lyr in self.canvas().layers():
                if isinstance(lyr, QgsVectorLayer) and lyr != active_layer:
                    if TrimExtendTool.candidate_scope == TrimExtendCandidateScope.LINES_ONLY:
                        if lyr.geometryType() == QgsWkbTypes.LineGeometry:
                            layers_to_check.append(lyr)
                    else:
                        if lyr.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                            layers_to_check.append(lyr)

        boundary_lines: List[List[Point2D]] = []

        for lyr in layers_to_check:
            is_active = (lyr == active_layer)
            # Transformuj zasięg canvas do CRS warstwy
            lyr_rect = self.to_layer_rect(lyr, canvas_extent)
            req = QgsFeatureRequest().setFilterRect(lyr_rect).setFlags(QgsFeatureRequest.ExactIntersect)

            for feat in lyr.getFeatures(req):
                if is_active and feat.id() == exclude_feat_id:
                    continue

                geom = feat.geometry()
                if geom.isEmpty():
                    continue

                # Jeśli polygon, wyciągnij pierścienie jako linie
                if geom.type() == QgsWkbTypes.PolygonGeometry:
                    geom = extract_rings_as_line(geom)
                    if geom.isEmpty():
                        continue

                # Transformuj geometrię do CRS aktywnej warstwy
                transformed_geom = self._transform_to_crs(geom, lyr.crs(), target_crs)
                if transformed_geom.isEmpty():
                    continue

                if transformed_geom.isMultipart():
                    for polyline in transformed_geom.asMultiPolyline():
                        if len(polyline) >= 2:
                            boundary_lines.append(qgs_points_to_tuples(polyline))
                else:
                    polyline = transformed_geom.asPolyline()
                    if len(polyline) >= 2:
                        boundary_lines.append(qgs_points_to_tuples(polyline))

        return boundary_lines

    def _transform_to_crs(self, geom: QgsGeometry, src_crs, dst_crs) -> QgsGeometry:
        if not src_crs.isValid() or not dst_crs.isValid() or src_crs == dst_crs:
            return QgsGeometry(geom)
        try:
            trans = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
            res_geom = QgsGeometry(geom)
            res_geom.transform(trans)
            return res_geom
        except Exception:
            return QgsGeometry(geom)

    def _set_status_tip(self, text: str):
        if self.iface:
            self.iface.mainWindow().statusBar().showMessage(text, 2500)
