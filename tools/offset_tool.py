#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Narzędzie interaktywnego offsetu (Prosty offset).
Autor: Mikołaj Sazonov
"""

import math
from enum import Enum
from typing import Optional, Tuple, List
from qgis.PyQt.QtCore import Qt, QPoint, QEvent
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import (
    QActionGroup,
    QWidgetAction,
    QMenu,
    QLabel
)
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
    QgsCoordinateTransform,
    QgsProject,
    Qgis,
    QgsMessageLog
)
from .base_curve_tool import BaseCurveTool
from ..gui.settings_widget import CurveSettingsWidget
from ..gui.offset_input_overlay import OffsetInputOverlay
from ..core.offset_utils import (
    compute_line_offset,
    compute_polygon_offset,
    extract_rings_as_line
)
from ..core.layer_modifier import LayerModifier


class OffsetCandidateScope(Enum):
    """Zakres wyszukiwania obiektów do offsetu."""
    ALL = "all"                 # Wszystkie obiekty (linie i poligony ze wszystkich warstw) [Domyślne]
    LINES_ONLY = "lines_only"   # Tylko obiekty liniowe (ze wszystkich warstw)
    ACTIVE_LAYER = "active"     # Tylko z aktualnej (edytowanej) warstwy


class OffsetTool(BaseCurveTool):
    """
    Narzędzie mapowe do dynamicznego prostego offsetu linii, polilinii oraz granic poligonów.
    Umożliwia przeciąganie myszą z podglądem na żywo (czerwona linia) lub bezpośrednie
    wpisanie odległości w pływającym okienku CAD i zatwierdzenie klawiszem Enter lub Tab.
    Nowy obiekt jest wstawiany do aktywnej edytowalnej warstwy QGIS (z obsługą Undo/Redo).
    """

    STATE_IDLE = 0
    STATE_DRAGGING = 1

    last_used_distance: Optional[float] = None
    candidate_scope: OffsetCandidateScope = OffsetCandidateScope.ALL

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget, iface=None):
        super().__init__(canvas, settings_widget)
        self.iface = iface
        self.state = self.STATE_IDLE

        # Pływający widget CAD do wprowadzania odległości
        self.overlay = OffsetInputOverlay(self.canvas())
        if OffsetTool.last_used_distance is not None:
            self.overlay.set_last_distance(OffsetTool.last_used_distance)
        self.overlay.distanceSubmitted.connect(self._on_overlay_distance_submitted)
        self.overlay.defaultDistanceRequested.connect(self._commit_offset)
        self.overlay.cancelled.connect(self._cancel_operation)

        # Gumka pomocnicza: linia pomiaru odległości od geometrii do kursora
        self.guide_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.guide_band.setColor(QColor(255, 120, 0, 180))
        self.guide_band.setWidth(1)

        # Stylizacja gumki podglądu kandydata (niebieska) i offsetu (czerwona)
        self.preview_band.setColor(QColor(235, 40, 40, 230))
        self.preview_band.setWidth(3)

        self.highlight_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.highlight_band.setColor(QColor(0, 140, 255, 200))
        self.highlight_band.setWidth(3)

        # Stan operacji
        self.target_geom: Optional[QgsGeometry] = None
        self.is_polygon_source: bool = False
        self.current_distance: float = 0.0
        self.current_signed_dist: float = 0.0
        self.current_offset_geom: Optional[QgsGeometry] = None
        self.hovered_candidate_geom: Optional[QgsGeometry] = None

    def activate(self):
        super().activate()
        # Instalacja filtra zdarzeń na płótnie mapy, aby klawisz Tab nie uciekał z canvasu
        self.canvas().installEventFilter(self)
        self.canvas().setFocus()

    def deactivate(self):
        try:
            self.canvas().removeEventFilter(self)
        except Exception as err:
            QgsMessageLog.logMessage(f"Event filter cleanup: {err}", "MSA: CurveMaster", Qgis.Info)
        if self.overlay:
            self.overlay.hide()
        super().deactivate()

    def eventFilter(self, obj, event):
        # Przechwytywanie klawisza Tab na poziomie QgsMapCanvas
        if obj == self.canvas() and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                if self.state == self.STATE_DRAGGING:
                    self.overlay._on_submit()
                # Zapobiegamy utracie fokusu klawiatury przez QgsMapCanvas
                self.canvas().setFocus()
                return True
        return super().eventFilter(obj, event)

    def create_dropdown_menu(self, parent=None) -> QMenu:
        """
        Tworzy rozwijane menu dla przycisku Offset (MenuButtonPopup),
        umożliwiające wybór zakresu wykrywanych obiektów.
        """
        menu = QMenu(parent or self.canvas())
        menu.setTitle("Zakres wykrywania obiektów")

        lbl_header = QLabel("  Wykrywaj obiekty do offsetu:")
        lbl_header.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
        act_header = QWidgetAction(menu)
        act_header.setDefaultWidget(lbl_header)
        menu.addAction(act_header)

        group = QActionGroup(menu)
        group.setExclusive(True)

        options = [
            ("Wszystkie obiekty (linie i poligony)", OffsetCandidateScope.ALL, "Wykrywaj linie, polilinie oraz granice poligonów ze wszystkich widocznych warstw"),
            ("Tylko obiekty liniowe", OffsetCandidateScope.LINES_ONLY, "Ogranicz wykrywanie tylko do linii i polilinii ze wszystkich warstw"),
            ("Tylko z aktualnej warstwy", OffsetCandidateScope.ACTIVE_LAYER, "Wykrywaj obiekty wyłącznie z warstwy, która jest aktualnie edytowana"),
        ]

        action_scope_map = []
        for label, scope, tooltip in options:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setToolTip(tooltip)
            act.setChecked(OffsetTool.candidate_scope == scope)
            group.addAction(act)

            def make_handler(s=scope):
                return lambda: self._set_candidate_scope(s)
            act.triggered.connect(make_handler(scope))
            action_scope_map.append((act, scope))

        def on_about_to_show():
            for a, s in action_scope_map:
                a.setChecked(OffsetTool.candidate_scope == s)

        menu.aboutToShow.connect(on_about_to_show)
        return menu

    def _set_candidate_scope(self, scope: OffsetCandidateScope):
        OffsetTool.candidate_scope = scope
        scope_names = {
            OffsetCandidateScope.ALL: "Wszystkie obiekty (linie i poligony)",
            OffsetCandidateScope.LINES_ONLY: "Tylko obiekty liniowe",
            OffsetCandidateScope.ACTIVE_LAYER: "Tylko aktualna edytowana warstwa"
        }
        name = scope_names.get(scope, "")
        self._set_status_tip(f"MSA Offset: Ustawiono zakres wykrywania: {name}")

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        active_layer = self.active_editable_layer()
        canvas_pt = e.mapPoint()

        if self.state == self.STATE_IDLE:
            # Wyszukiwanie obiektu do odsunięcia pod kursorem
            segment_only = bool(e.modifiers() & Qt.ControlModifier)
            candidate = self._find_candidate_near(canvas_pt, segment_only=segment_only)

            if candidate:
                cand_geom, is_poly = candidate
                self.hovered_candidate_geom = cand_geom
                self._display_geometry_in_band(self.highlight_band, cand_geom, active_layer)
                msg = "MSA Offset: Kliknij, aby wybrać obiekt do odsunięcia."
                if segment_only:
                    msg += " [Tryb: tylko kliknięty segment]"
                else:
                    msg += " [Przytrzymaj Ctrl dla segmentu]"
                self._set_status_tip(msg)
            else:
                self.hovered_candidate_geom = None
                self.highlight_band.reset(QgsWkbTypes.LineGeometry)
                if not active_layer:
                    self._set_status_tip("MSA Offset: Włącz tryb edycji dla warstwy liniowej lub poligonowej.")
                else:
                    self._set_status_tip("MSA Offset: Najedź na obiekt do odsunięcia.")

        elif self.state == self.STATE_DRAGGING:
            if not self.target_geom or self.target_geom.isEmpty():
                return

            layer_pt = self.to_layer_point(active_layer, canvas_pt) if active_layer else canvas_pt

            # Obliczenie geometrii offsetu w układzie CRS warstwy
            if self.is_polygon_source:
                off_geom, dist, signed_dist = compute_polygon_offset(self.target_geom, layer_pt)
            else:
                off_geom, dist, signed_dist = compute_line_offset(self.target_geom, layer_pt)

            self.current_distance = dist
            self.current_signed_dist = signed_dist
            self.current_offset_geom = off_geom

            # Aktualizacja czerwonego podglądu na mapie
            self._display_geometry_in_band(self.preview_band, off_geom, active_layer)

            # Rysowanie linii pomocniczej od punktu bazowego do kursora
            self._update_guide_line(layer_pt, active_layer)

            # Aktualizacja pływającego okienka CAD
            self.overlay.set_current_distance(dist)
            self.overlay.update_position(e.pos(), self.canvas().rect())
            self.overlay.show()

            if OffsetTool.last_used_distance is not None and OffsetTool.last_used_distance > 0:
                self._set_status_tip(
                    f"MSA Offset: Dystans myszy = {dist:.2f} m. [Enter/Tab = <{OffsetTool.last_used_distance:.2f}> m, Klik = mysz, Esc = Anuluj]"
                )
            else:
                self._set_status_tip(
                    f"MSA Offset: Dystans = {dist:.2f} m. Kliknij lub [Enter/Tab], aby zatwierdzić. [Esc = Anuluj]"
                )

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.RightButton:
            self._cancel_operation()
            return

        if e.button() != Qt.LeftButton:
            return

        active_layer = self.active_editable_layer()
        if not active_layer:
            if self.iface:
                self.iface.messageBar().pushWarning(
                    "MSA: CurveMaster",
                    "Wybierz warstwę liniową lub poligonową i włącz tryb edycji, aby utworzyć obiekt offsetu."
                )
            return

        canvas_pt = e.mapPoint()

        if self.state == self.STATE_IDLE:
            segment_only = bool(e.modifiers() & Qt.ControlModifier)
            candidate = self._find_candidate_near(canvas_pt, segment_only=segment_only)
            if not candidate:
                return

            cand_geom, is_poly = candidate
            self.target_geom = cand_geom
            self.is_polygon_source = is_poly
            self.state = self.STATE_DRAGGING

            # Przełącz podgląd z niebieskiego na czerwony
            self.highlight_band.reset(QgsWkbTypes.LineGeometry)
            if OffsetTool.last_used_distance is not None:
                self.overlay.set_last_distance(OffsetTool.last_used_distance)
            self.overlay.update_position(e.pos(), self.canvas().rect())
            self.overlay.show()
            self.canvas().setFocus()

        elif self.state == self.STATE_DRAGGING:
            # Zatwierdzenie bieżącej pozycji kliknięciem myszy
            self._commit_offset()

    def _on_overlay_distance_submitted(self, distance_val: float):
        """Zatwierdzenie dokładnej odległości wpisanej w okienku CAD lub powtórzonej klawiszem Enter/Tab."""
        if not self.target_geom or self.target_geom.isEmpty():
            return

        active_layer = self.active_editable_layer()
        if not active_layer:
            return

        # Ustal znak odsunięcia zgodnie z bieżącym kierunkiem kursora
        sign = -1.0 if self.current_signed_dist < 0 else 1.0
        target_dist = abs(distance_val) * sign

        if self.is_polygon_source:
            off_geom = self.target_geom.buffer(target_dist, 8, Qgis.EndCapStyle.Flat, Qgis.JoinStyle.Miter, 2.0)
            if off_geom.isNull() or off_geom.isEmpty():
                off_geom = self.target_geom.buffer(target_dist, 8, Qgis.EndCapStyle.Flat, Qgis.JoinStyle.Round, 2.0)
        else:
            off_geom = self.target_geom.offsetCurve(target_dist, 8, Qgis.JoinStyle.Miter, 2.0)
            if off_geom.isNull() or off_geom.isEmpty():
                off_geom = self.target_geom.offsetCurve(target_dist, 8, Qgis.JoinStyle.Round, 2.0)

        self.current_offset_geom = off_geom
        self.current_distance = abs(distance_val)
        OffsetTool.last_used_distance = self.current_distance
        self.overlay.set_last_distance(self.current_distance)
        self._commit_offset()

    def _commit_offset(self):
        """Zapisuje nowy obiekt do aktywnej warstwy edytowalnej."""
        active_layer = self.active_editable_layer()
        if not active_layer:
            self._cancel_operation()
            return

        if self.current_offset_geom is None or self.current_offset_geom.isEmpty():
            self._cancel_operation()
            return

        geom_to_add = QgsGeometry(self.current_offset_geom)

        # Jeśli warstwa jest liniowa, a offset powstał z poligonu, wyciągnij pierścień jako linię
        if active_layer.geometryType() == QgsWkbTypes.LineGeometry and geom_to_add.type() == QgsWkbTypes.PolygonGeometry:
            geom_to_add = extract_rings_as_line(geom_to_add)

        feat_id = LayerModifier.add_feature(
            layer=active_layer,
            geom=geom_to_add,
            command_name=f"MSA: Utwórz offset ({self.current_distance:.2f} m)"
        )

        if feat_id is not None:
            if self.current_distance > 0:
                OffsetTool.last_used_distance = self.current_distance
                self.overlay.set_last_distance(self.current_distance)
            if self.iface:
                self.iface.messageBar().pushInfo(
                    "MSA: CurveMaster",
                    f"Utworzono nowy obiekt offsetu o odległości {self.current_distance:.2f} m."
                )

        self._cancel_operation()

    def _cancel_operation(self):
        """Resetuje stan narzędzia do oczekiwania (STATE_IDLE)."""
        self.state = self.STATE_IDLE
        self.target_geom = None
        self.is_polygon_source = False
        self.current_distance = 0.0
        self.current_signed_dist = 0.0
        self.current_offset_geom = None
        self.hovered_candidate_geom = None

        self.clear_preview()
        if self.guide_band:
            self.guide_band.reset(QgsWkbTypes.LineGeometry)
        if self.overlay:
            self.overlay.hide()
            self.overlay.edit.clear()
            if OffsetTool.last_used_distance is not None:
                self.overlay.set_last_distance(OffsetTool.last_used_distance)

        self.canvas().setFocus()

    def clear_preview(self):
        super().clear_preview()
        if hasattr(self, 'highlight_band') and self.highlight_band:
            self.highlight_band.reset(QgsWkbTypes.LineGeometry)
        if hasattr(self, 'guide_band') and self.guide_band:
            self.guide_band.reset(QgsWkbTypes.LineGeometry)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel_operation()
            return

        if self.state == self.STATE_DRAGGING:
            key_text = e.text()
            if key_text and (key_text.isdigit() or key_text in ('.', ',')):
                self.overlay.activate_with_text(key_text)
                return
            elif e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                self.overlay._on_submit()
                return

        super().keyPressEvent(e)

    def _update_guide_line(self, layer_pt: QgsPointXY, active_layer: Optional[QgsVectorLayer]):
        """Rysuje linię pomocniczą łączącą rzut punktu na geometrii z kursorem."""
        if not self.target_geom or self.target_geom.isEmpty():
            self.guide_band.reset(QgsWkbTypes.LineGeometry)
            return

        sqr_dist, min_pt, after_v, left_of = self.target_geom.closestSegmentWithContext(layer_pt)
        p_base_canvas = self.to_canvas_point(active_layer, min_pt) if active_layer else min_pt
        p_cursor_canvas = self.to_canvas_point(active_layer, layer_pt) if active_layer else layer_pt

        guide_geom = QgsGeometry.fromPolylineXY([p_base_canvas, p_cursor_canvas])
        self.guide_band.setToGeometry(guide_geom, None)

    def _display_geometry_in_band(self, band: QgsRubberBand, geom: QgsGeometry, layer: Optional[QgsVectorLayer]):
        """Renderuje geometrię na gumce podglądu z poprawną transformacją CRS."""
        if geom is None or geom.isEmpty():
            band.reset(QgsWkbTypes.LineGeometry)
            return

        canvas_crs = self._canvas.mapSettings().destinationCrs()
        if layer and layer.crs().isValid() and canvas_crs.isValid() and layer.crs() != canvas_crs:
            try:
                trans = QgsCoordinateTransform(layer.crs(), canvas_crs, QgsProject.instance())
                canvas_geom = QgsGeometry(geom)
                canvas_geom.transform(trans)
            except Exception:
                canvas_geom = geom
        else:
            canvas_geom = geom

        band_type = QgsWkbTypes.PolygonGeometry if canvas_geom.type() == QgsWkbTypes.PolygonGeometry else QgsWkbTypes.LineGeometry
        band.reset(band_type)
        band.setToGeometry(canvas_geom, None)

    def _find_candidate_near(
        self,
        canvas_point: QgsPointXY,
        segment_only: bool = False
    ) -> Optional[Tuple[QgsGeometry, bool]]:
        """
        Wyszukuje najbliższą linię, polilinię lub poligon pod kursorem z uwzględnieniem
        wybranego zakresu candidate_scope (wszystkie, tylko linie, tylko aktywna warstwa).
        Zwraca: (QgsGeometry w układzie aktywnej warstwy, is_polygon: bool)
        """
        active_layer = self.active_editable_layer()
        target_crs = active_layer.crs() if active_layer else self._canvas.mapSettings().destinationCrs()

        mupp = self._canvas.mapUnitsPerPixel()
        tol_canvas = mupp * 20.0  # 20 px tolerancji

        layers_to_check: List[QgsVectorLayer] = []
        if active_layer:
            layers_to_check.append(active_layer)

        # Jeśli zakres nie ogranicza się wyłącznie do aktywnej warstwy, przeszukaj pozostałe widoczne
        if OffsetTool.candidate_scope != OffsetCandidateScope.ACTIVE_LAYER:
            for lyr in self._canvas.layers():
                if isinstance(lyr, QgsVectorLayer) and lyr != active_layer:
                    if OffsetTool.candidate_scope == OffsetCandidateScope.LINES_ONLY:
                        if lyr.geometryType() == QgsWkbTypes.LineGeometry:
                            layers_to_check.append(lyr)
                    else:
                        if lyr.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                            layers_to_check.append(lyr)

        best_dist_canvas = float('inf')
        best_candidate: Optional[Tuple[QgsGeometry, bool]] = None

        search_rect_canvas = QgsRectangle(
            canvas_point.x() - tol_canvas,
            canvas_point.y() - tol_canvas,
            canvas_point.x() + tol_canvas,
            canvas_point.y() + tol_canvas
        )

        for lyr in layers_to_check:
            search_rect_lyr = self.to_layer_rect(lyr, search_rect_canvas)
            req = QgsFeatureRequest().setFilterRect(search_rect_lyr).setFlags(QgsFeatureRequest.ExactIntersect)

            for feat in lyr.getFeatures(req):
                geom = feat.geometry()
                if geom.isEmpty():
                    continue

                gtype = geom.type()
                is_poly = (gtype == QgsWkbTypes.PolygonGeometry)

                # Jeśli wybrano zakres tylko obiekty liniowe, ignoruj poligony
                if OffsetTool.candidate_scope == OffsetCandidateScope.LINES_ONLY and is_poly:
                    continue

                # Wyznaczenie punktu rzutu kursora w CRS warstwy
                pt_in_lyr = self.to_layer_point(lyr, canvas_point)

                # Dla poligonu badamy odległość do krawędzi zewnętrznej
                boundary = extract_rings_as_line(geom) if is_poly else geom

                if boundary.isEmpty():
                    continue

                sqr_dist, min_pt, after_vertex, left_of = boundary.closestSegmentWithContext(pt_in_lyr)
                min_pt_canvas = self.to_canvas_point(lyr, min_pt)
                dist_canvas = math.hypot(canvas_point.x() - min_pt_canvas.x(), canvas_point.y() - min_pt_canvas.y())

                if dist_canvas <= tol_canvas and dist_canvas < best_dist_canvas:
                    best_dist_canvas = dist_canvas

                    if segment_only:
                        # Pobierz tylko pojedynczy odcinek
                        start_v_nr = after_vertex - 1
                        end_v_nr = after_vertex
                        if start_v_nr >= 0:
                            p_a = boundary.vertexAt(start_v_nr)
                            p_b = boundary.vertexAt(end_v_nr)
                            # Konwersja QgsPoint na QgsPointXY
                            seg_geom = QgsGeometry.fromPolylineXY([QgsPointXY(p_a), QgsPointXY(p_b)])
                            # Transformacja do CRS warstwy aktywnej
                            final_geom = self._transform_to_target_crs(seg_geom, lyr.crs(), target_crs)
                            best_candidate = (final_geom, False)
                    else:
                        # Pełna geometria (linia lub poligon)
                        final_geom = self._transform_to_target_crs(geom, lyr.crs(), target_crs)
                        best_candidate = (final_geom, is_poly)

        return best_candidate

    def _transform_to_target_crs(self, geom: QgsGeometry, src_crs, dst_crs) -> QgsGeometry:
        """Przekształca geometrię między układami współrzędnych."""
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
        """Ustawia podpowiedź w pasku stanu QGIS."""
        if self.iface:
            self.iface.mainWindow().statusBar().showMessage(text, 3000)
