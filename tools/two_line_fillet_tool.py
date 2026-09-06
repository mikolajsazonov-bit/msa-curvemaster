#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Narzędzie zaokrąglania narożnika dwóch linii (Two-Line Fillet).
Umożliwia:
- Zaznaczenie dwóch linii przecinających się (lub których proste się przecinają).
- Wrysowanie łuku o zadanym promieniu (wpisanym ręcznie, wybranym myszką wizualnie lub zapamiętanym poprzednim).
- Automatyczny trim: odcięcie nadmiaru linii sięgających do łuku, lub rozcięcie linii przelotowych z wycięciem klina do przecięcia.
- Scalenie narożnika w jedną ciągłą polilinię.
Autor: Mikołaj Sazonov
"""

import math
from typing import Optional, Tuple, List
from qgis.PyQt.QtCore import Qt, QPoint, QEvent
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QActionGroup,
    QWidgetAction,
    QMenu,
    QLabel
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
from ..gui.radius_input_overlay import RadiusInputOverlay
from ..core.geometry_utils import (
    Point2D,
    distance,
    SamplingMode,
    fillet_two_lines_2d,
    FilletTwoLinesResult
)
from ..core.layer_modifier import LayerModifier, qgs_points_to_tuples, tuples_to_qgs_points
try:
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.i18n import tr


class TwoLineFilletTool(BaseCurveTool):
    """
    Narzędzie mapowe do zaokrąglania narożnika między dwoma liniami z automatycznym przycięciem (Trim).
    """

    STATE_SELECT_FIRST = 0
    STATE_SELECT_SECOND = 1
    STATE_ADJUST_RADIUS = 2

    last_used_radius: float = 5.0
    join_corner_lines: bool = True

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget, iface=None):
        super().__init__(canvas, settings_widget)
        self.iface = iface
        self.state = self.STATE_SELECT_FIRST

        # Pływający widget CAD do wprowadzania promienia
        self.overlay = RadiusInputOverlay(self.canvas())
        self.overlay.set_last_radius(TwoLineFilletTool.last_used_radius)
        self.overlay.radiusSubmitted.connect(self._on_overlay_radius_submitted)
        self.overlay.cancelled.connect(self._cancel_operation)

        # Gumka do podświetlenia pierwszej wybranej linii (niebieska)
        self.line1_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.line1_band.setColor(QColor(0, 140, 255, 200))
        self.line1_band.setWidth(3)

        # Gumka do podświetlenia drugiej linii (błękitna)
        self.line2_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.line2_band.setColor(QColor(0, 200, 255, 180))
        self.line2_band.setWidth(2)

        # Gumka podglądu łuku i wynikowej geometrii (czerwona)
        self.preview_band.setColor(QColor(235, 40, 40, 230))
        self.preview_band.setWidth(3)

        # Gumka do podglądu wycinanego klina / fragmentu usuwanego (przerywana czerwona / pomarańczowa)
        self.trim_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.trim_band.setColor(QColor(255, 120, 0, 200))
        self.trim_band.setWidth(2)

        # Wskaźnik przyciągania QGIS
        self.snap_indicator = QgsSnapIndicator(self.canvas())

        # Stan operacji
        self.line1_feat_id: Optional[int] = None
        self.line1_part_idx: int = 0
        self.line1_pts: List[Point2D] = []
        self.line1_click_pt: Optional[Point2D] = None

        self.line2_feat_id: Optional[int] = None
        self.line2_part_idx: int = 0
        self.line2_pts: List[Point2D] = []
        self.line2_click_pt: Optional[Point2D] = None

        self.current_result: Optional[FilletTwoLinesResult] = None
        self.current_radius: float = TwoLineFilletTool.last_used_radius

    def activate(self):
        super().activate()
        self.canvas().installEventFilter(self)
        self.canvas().setFocus()
        self._cancel_operation()

    def deactivate(self):
        try:
            self.canvas().removeEventFilter(self)
        except Exception as err:
            QgsMessageLog.logMessage(f"Event filter cleanup: {err}", "MSA: CurveMaster", Qgis.Info)
        if self.overlay:
            self.overlay.hide()
        self.clear_preview()
        super().deactivate()

    def eventFilter(self, obj, event):
        if obj == self.canvas() and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                if self.state in (self.STATE_SELECT_SECOND, self.STATE_ADJUST_RADIUS):
                    self.overlay._on_submit()
                self.canvas().setFocus()
                return True
        return super().eventFilter(obj, event)

    def create_dropdown_menu(self, parent=None) -> QMenu:
        """Menu ustawień zaokrąglenia dwóch linii."""
        menu = QMenu(parent or self.canvas())
        menu.setTitle(tr("Two-Line Fillet Settings", "Ustawienia zaokrąglania dwóch linii"))

        lbl_header = QLabel(tr("  Fillet options:", "  Opcje zaokrąglenia (Fillet):"))
        lbl_header.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
        act_header = QWidgetAction(menu)
        act_header.setDefaultWidget(lbl_header)
        menu.addAction(act_header)

        # Przełącznik scalania narożników
        act_join = menu.addAction(tr("Join corner lines into single polyline", "Scalaj narożniki w jedną polilinię"))
        act_join.setCheckable(True)
        act_join.setChecked(TwoLineFilletTool.join_corner_lines)
        act_join.toggled.connect(self._toggle_join_corners)

        menu.addSeparator()

        # Opcje próbkowania łuku
        lbl_samp = QLabel(tr("  Sampling method:", "  Metoda próbkowania łuku:"))
        lbl_samp.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
        act_samp = QWidgetAction(menu)
        act_samp.setDefaultWidget(lbl_samp)
        menu.addAction(act_samp)

        modes = [
            (tr("Chord length (m)", "Długość odcinka (m)"), SamplingMode.LINEAR_STEP),
            (tr("Angular step (°)", "Krok kątowy (°)"), SamplingMode.ANGULAR_STEP),
            (tr("Max sagitta (m)", "Odchyłka/Strzałka (m)"), SamplingMode.MAX_SAGITTA),
        ]
        for label, smode in modes:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.settings().sampling_mode() == smode)
            def make_h(m=smode):
                return lambda: self.settings().combo_mode.setCurrentIndex(self.settings().combo_mode.findData(m))
            act.triggered.connect(make_h(smode))

        return menu

    def _toggle_join_corners(self, checked: bool):
        TwoLineFilletTool.join_corner_lines = checked
        msg = tr("Fillet: Join corner lines enabled.", "Fillet: Włączono scalanie narożników w jedną polilinię.") if checked else tr("Fillet: Join corner lines disabled.", "Fillet: Wyłączono scalanie narożników.")
        self._set_status_tip(msg)

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        active_layer = self.active_editable_layer()
        if not active_layer or active_layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.clear_preview()
            self._set_status_tip(tr("MSA Fillet: Select an editable line layer.", "MSA Fillet: Wybierz edytowalną warstwę liniową."))
            return

        canvas_pt = e.mapPoint()
        layer_pt = self.to_layer_point(active_layer, canvas_pt)

        # Sprawdzenie przyciągania
        match = self.canvas().snappingUtils().snapToMap(e.pos())
        if match.isValid():
            self.snap_indicator.setMatch(match)
            self.snap_indicator.setVisible(True)
        else:
            self.snap_indicator.setVisible(False)

        if self.state == self.STATE_SELECT_FIRST:
            target = self._find_line_near(active_layer, canvas_pt, layer_pt)
            if target:
                feat_id, part, pts, seg = target
                canvas_pts = self.to_canvas_points_list(active_layer, pts)
                self.line1_band.reset(QgsWkbTypes.LineGeometry)
                for pt in canvas_pts:
                    self.line1_band.addPoint(pt)
                self._set_status_tip(tr(
                    "MSA Fillet: Click first line to fillet.",
                    "MSA Fillet: Kliknij pierwszą linię do zaokrąglenia."
                ))
            else:
                self.line1_band.reset(QgsWkbTypes.LineGeometry)
                self._set_status_tip(tr(
                    "MSA Fillet: Hover over first line.",
                    "MSA Fillet: Najedź na pierwszą linię do zaokrąglenia."
                ))

        elif self.state == self.STATE_SELECT_SECOND:
            target = self._find_line_near(active_layer, canvas_pt, layer_pt, exclude_feat_id=None)
            if target:
                feat_id, part, pts, seg = target
                # Jeśli to ta sama linia i ten sam segment, pomiń
                if feat_id == self.line1_feat_id and len(pts) <= 2:
                    self.line2_band.reset(QgsWkbTypes.LineGeometry)
                    return

                self.line2_feat_id = feat_id
                self.line2_part_idx = part
                self.line2_pts = pts
                self.line2_click_pt = (layer_pt.x(), layer_pt.y())

                # Podświetl linię 2
                canvas_pts2 = self.to_canvas_points_list(active_layer, pts)
                self.line2_band.reset(QgsWkbTypes.LineGeometry)
                for pt in canvas_pts2:
                    self.line2_band.addPoint(pt)

                # Oblicz podgląd zaokrąglenia
                self._update_fillet_preview(active_layer, e.pos())
            else:
                self.line2_band.reset(QgsWkbTypes.LineGeometry)
                self.preview_band.reset(QgsWkbTypes.LineGeometry)
                self.trim_band.reset(QgsWkbTypes.LineGeometry)
                self.current_result = None
                self._set_status_tip(tr(
                    "MSA Fillet: Select second line [Enter = default radius, Esc = Cancel].",
                    f"MSA Fillet: Wybierz drugą linię [Enter/Tab = <{TwoLineFilletTool.last_used_radius:.2f}> m, Esc = Anuluj]."
                ))

        elif self.state == self.STATE_ADJUST_RADIUS:
            if not self.line1_pts or not self.line2_pts or not self.current_result:
                return

            # Dynamiczne dopasowanie promienia do pozycji myszy
            apex = self.current_result.apex
            d_mouse = math.hypot(layer_pt.x() - apex[0], layer_pt.y() - apex[1])
            eff_r = min(max(0.1, d_mouse * 0.7), 10000.0)
            self.current_radius = eff_r

            self._recalculate_and_preview(active_layer, eff_r, e.pos())

    def _update_fillet_preview(self, layer: QgsVectorLayer, screen_pos: QPoint):
        if not self.line1_pts or not self.line2_pts or not self.line1_click_pt or not self.line2_click_pt:
            return

        mode = self.settings().sampling_mode()
        step_val = self.settings().step_value()

        res = fillet_two_lines_2d(
            pts1=self.line1_pts,
            click1=self.line1_click_pt,
            pts2=self.line2_pts,
            click2=self.line2_click_pt,
            radius=self.current_radius,
            mode=mode,
            step_value=step_val,
            is_same_line=(self.line1_feat_id == self.line2_feat_id)
        )

        if res is not None:
            self.current_result = res

            # Renderuj łuk na czerwono
            arc_canvas = self.to_canvas_points_list(layer, res.arc_points)
            self.preview_band.reset(QgsWkbTypes.LineGeometry)
            for pt in arc_canvas:
                self.preview_band.addPoint(pt)

            # Renderuj przycinany klin/odcinki do usunięcia na pomarańczowo
            trim_pts = [res.t1, res.apex, res.t2]
            trim_canvas = self.to_canvas_points_list(layer, trim_pts)
            self.trim_band.reset(QgsWkbTypes.LineGeometry)
            for pt in trim_canvas:
                self.trim_band.addPoint(pt)

            # Aktualizuj HUD
            self.overlay.set_current_radius(res.radius)
            self.overlay.update_position(screen_pos, self.canvas().rect())
            self.overlay.show()

            self._set_status_tip(tr(
                f"MSA Fillet: Radius = {res.radius:.2f} m. Click to choose line 2 / confirm [Enter = <{TwoLineFilletTool.last_used_radius:.2f}> m].",
                f"MSA Fillet: Promień = {res.radius:.2f} m. Kliknij, aby wybrać linię 2 [Enter/Tab = <{TwoLineFilletTool.last_used_radius:.2f}> m, wpisz liczbę = zmień promień]."
            ))
        else:
            self.preview_band.reset(QgsWkbTypes.LineGeometry)
            self.trim_band.reset(QgsWkbTypes.LineGeometry)
            self.current_result = None

    def _recalculate_and_preview(self, layer: QgsVectorLayer, radius_val: float, screen_pos: QPoint):
        mode = self.settings().sampling_mode()
        step_val = self.settings().step_value()

        res = fillet_two_lines_2d(
            pts1=self.line1_pts,
            click1=self.line1_click_pt,
            pts2=self.line2_pts,
            click2=self.line2_click_pt,
            radius=radius_val,
            mode=mode,
            step_value=step_val,
            is_same_line=(self.line1_feat_id == self.line2_feat_id)
        )

        if res is not None:
            self.current_result = res
            arc_canvas = self.to_canvas_points_list(layer, res.arc_points)
            self.preview_band.reset(QgsWkbTypes.LineGeometry)
            for pt in arc_canvas:
                self.preview_band.addPoint(pt)

            trim_pts = [res.t1, res.apex, res.t2]
            trim_canvas = self.to_canvas_points_list(layer, trim_pts)
            self.trim_band.reset(QgsWkbTypes.LineGeometry)
            for pt in trim_canvas:
                self.trim_band.addPoint(pt)

            self.overlay.set_current_radius(res.radius)
            self.overlay.update_position(screen_pos, self.canvas().rect())
            self.overlay.show()

            self._set_status_tip(tr(
                f"MSA Fillet (Drag): Radius = {res.radius:.2f} m. Click to confirm [Enter = <{TwoLineFilletTool.last_used_radius:.2f}> m].",
                f"MSA Fillet (Wizualny): Promień = {res.radius:.2f} m. Kliknij, aby zatwierdzić [Enter = <{TwoLineFilletTool.last_used_radius:.2f}> m, Esc = Anuluj]."
            ))

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.RightButton:
            self._cancel_operation()
            return

        if e.button() != Qt.LeftButton:
            return

        active_layer = self.active_editable_layer()
        if not active_layer:
            return

        canvas_pt = e.mapPoint()
        layer_pt = self.to_layer_point(active_layer, canvas_pt)

        if self.state == self.STATE_SELECT_FIRST:
            target = self._find_line_near(active_layer, canvas_pt, layer_pt)
            if not target:
                return
            feat_id, part, pts, seg = target
            self.line1_feat_id = feat_id
            self.line1_part_idx = part
            self.line1_pts = pts
            self.line1_click_pt = (layer_pt.x(), layer_pt.y())

            # Utrwal podświetlenie linii 1
            canvas_pts = self.to_canvas_points_list(active_layer, pts)
            self.line1_band.reset(QgsWkbTypes.LineGeometry)
            for pt in canvas_pts:
                self.line1_band.addPoint(pt)

            self.state = self.STATE_SELECT_SECOND
            self.overlay.set_last_radius(TwoLineFilletTool.last_used_radius)
            self.overlay.update_position(e.pos(), self.canvas().rect())
            self.overlay.show()
            self._set_status_tip(tr(
                "MSA Fillet: Click second line to fillet.",
                "MSA Fillet: Kliknij drugą linię do zaokrąglenia."
            ))

        elif self.state == self.STATE_SELECT_SECOND:
            target = self._find_line_near(active_layer, canvas_pt, layer_pt, exclude_feat_id=None)
            if target:
                feat_id, part, pts, seg = target
                if not (feat_id == self.line1_feat_id and len(pts) <= 2):
                    self.line2_feat_id = feat_id
                    self.line2_part_idx = part
                    self.line2_pts = pts
                    self.line2_click_pt = (layer_pt.x(), layer_pt.y())
                    mode = self.settings().sampling_mode()
                    step_val = self.settings().step_value()
                    self.current_result = fillet_two_lines_2d(
                        pts1=self.line1_pts,
                        click1=self.line1_click_pt,
                        pts2=self.line2_pts,
                        click2=self.line2_click_pt,
                        radius=self.current_radius,
                        mode=mode,
                        step_value=step_val,
                        is_same_line=(self.line1_feat_id == self.line2_feat_id)
                    )

            if not self.current_result:
                return

            if self.settings().is_interactive_fillet():
                # Przejście w tryb wizualnego dopasowywania promienia
                self.state = self.STATE_ADJUST_RADIUS
                self._set_status_tip(tr(
                    "MSA Fillet: Move mouse to adjust radius visually, click to confirm.",
                    "MSA Fillet: Przesuń mysz, aby wizualnie dopasować promień, kliknij aby zatwierdzić."
                ))
            else:
                self._commit_fillet()

        elif self.state == self.STATE_ADJUST_RADIUS:
            self._commit_fillet()

    def _on_overlay_radius_submitted(self, radius_val: float):
        """Wpisanie promienia z klawiatury lub zatwierdzenie domyślnego klawiszem Enter/Tab."""
        active_layer = self.active_editable_layer()
        if not active_layer or not self.line1_pts or not self.line2_pts or not self.line1_click_pt or not self.line2_click_pt:
            return

        self.current_radius = radius_val
        mode = self.settings().sampling_mode()
        step_val = self.settings().step_value()

        res = fillet_two_lines_2d(
            pts1=self.line1_pts,
            click1=self.line1_click_pt,
            pts2=self.line2_pts,
            click2=self.line2_click_pt,
            radius=radius_val,
            mode=mode,
            step_value=step_val,
            is_same_line=(self.line1_feat_id == self.line2_feat_id)
        )
        if res is not None:
            self.current_result = res
            self._commit_fillet()

    def _commit_fillet(self):
        """Zapisanie wyniku zaokrąglenia i trimu do warstwy QGIS."""
        active_layer = self.active_editable_layer()
        if not active_layer or not self.current_result:
            self._cancel_operation()
            return

        res = self.current_result
        TwoLineFilletTool.last_used_radius = res.radius
        self.overlay.set_last_radius(res.radius)

        layer_is_multi = QgsWkbTypes.isMultiType(active_layer.wkbType())

        active_layer.beginEditCommand(tr(f"MSA: Two-line fillet (R={res.radius:.2f} m)",
                                         f"MSA: Zaokrąglij dwie linie (R={res.radius:.2f} m)"))

        is_same_feat = (self.line2_feat_id == self.line1_feat_id)

        # SCENARIUSZ 1: Narożnik (żadna linia nie kontynuuje się) + włączone scalanie w jedną polilinię (lub ta sama linia)
        if (not res.line1_continues and not res.line2_continues and (TwoLineFilletTool.join_corner_lines or is_same_feat)) and res.joined_corner:
            g_joined = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(res.joined_corner))
            ad_joined = LayerModifier.adapt_geometry_to_layer(active_layer, g_joined)
            if ad_joined:
                # Nadpisz obiekt 1 scaloną polilinią
                active_layer.changeGeometry(self.line1_feat_id, ad_joined[0])
                # Jeśli to były dwa różne obiekty, usuń obiekt 2
                if not is_same_feat:
                    active_layer.deleteFeature(self.line2_feat_id)

        # SCENARIUSZ 2: Linie z kontynuacją lub wyłączone scalanie
        else:
            # 1. Zmiana linii 1
            # Część zachowana linii 1 rozszerzona o łuk sięgający do t2 (dla zachowania ciągłości skrętu)
            p1_with_arc = list(res.line1_kept)
            for pt in res.arc_points:
                if distance(p1_with_arc[-1], pt) > 1e-4:
                    p1_with_arc.append(pt)

            g1_kept = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(p1_with_arc))
            ad1_kept = LayerModifier.adapt_geometry_to_layer(active_layer, g1_kept)
            if ad1_kept:
                active_layer.changeGeometry(self.line1_feat_id, ad1_kept[0])

            # Jeśli linia 1 ma kontynuację za skrzyżowaniem
            if res.line1_continues and res.line1_continuation:
                g1_cont = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(res.line1_continuation))
                ad1_cont = LayerModifier.adapt_geometry_to_layer(active_layer, g1_cont)
                if ad1_cont:
                    feat1 = active_layer.getFeature(self.line1_feat_id)
                    new_f1 = QgsFeature(active_layer.fields())
                    if feat1.isValid():
                        new_f1.setAttributes(LayerModifier.copy_attributes_for_new_feature(active_layer, feat1))
                    new_f1.setGeometry(ad1_cont[0])
                    active_layer.addFeature(new_f1)

            # 2. Zmiana linii 2 (jeśli to inny obiekt)
            if self.line2_feat_id != self.line1_feat_id:
                g2_kept = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(res.line2_kept))
                ad2_kept = LayerModifier.adapt_geometry_to_layer(active_layer, g2_kept)
                if ad2_kept:
                    active_layer.changeGeometry(self.line2_feat_id, ad2_kept[0])

                # Jeśli linia 2 ma kontynuację za skrzyżowaniem
                if res.line2_continues and res.line2_continuation:
                    g2_cont = QgsGeometry.fromPolylineXY(tuples_to_qgs_points(res.line2_continuation))
                    ad2_cont = LayerModifier.adapt_geometry_to_layer(active_layer, g2_cont)
                    if ad2_cont:
                        feat2 = active_layer.getFeature(self.line2_feat_id)
                        new_f2 = QgsFeature(active_layer.fields())
                        if feat2.isValid():
                            new_f2.setAttributes(LayerModifier.copy_attributes_for_new_feature(active_layer, feat2))
                        new_f2.setGeometry(ad2_cont[0])
                        active_layer.addFeature(new_f2)

        active_layer.endEditCommand()
        active_layer.triggerRepaint()

        if self.iface:
            self.iface.messageBar().pushInfo(
                "MSA: CurveMaster",
                tr(f"Fillet completed with radius {res.radius:.2f} m.",
                   f"Utworzono zaokrąglenie dwóch linii o promieniu {res.radius:.2f} m.")
            )

        self._cancel_operation()

    def _cancel_operation(self):
        self.state = self.STATE_SELECT_FIRST
        self.line1_feat_id = None
        self.line1_pts = []
        self.line1_click_pt = None
        self.line2_feat_id = None
        self.line2_pts = []
        self.line2_click_pt = None
        self.current_result = None

        self.clear_preview()
        if self.overlay:
            self.overlay.hide()
            self.overlay.edit.clear()
            self.overlay.set_last_radius(TwoLineFilletTool.last_used_radius)
        self.canvas().setFocus()

    def clear_preview(self):
        super().clear_preview()
        if hasattr(self, 'line1_band') and self.line1_band:
            self.line1_band.reset(QgsWkbTypes.LineGeometry)
        if hasattr(self, 'line2_band') and self.line2_band:
            self.line2_band.reset(QgsWkbTypes.LineGeometry)
        if hasattr(self, 'trim_band') and self.trim_band:
            self.trim_band.reset(QgsWkbTypes.LineGeometry)
        if hasattr(self, 'snap_indicator') and self.snap_indicator:
            self.snap_indicator.setVisible(False)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel_operation()
            return

        if self.state in (self.STATE_SELECT_SECOND, self.STATE_ADJUST_RADIUS):
            key_text = e.text()
            if key_text and (key_text.isdigit() or key_text in ('.', ',')):
                self.overlay.activate_with_text(key_text)
                return
            elif e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                self.overlay._on_submit()
                return

        super().keyPressEvent(e)

    def _find_line_near(
        self,
        layer: QgsVectorLayer,
        canvas_pt: QgsPointXY,
        layer_pt: QgsPointXY,
        exclude_feat_id: Optional[int] = None
    ) -> Optional[Tuple[int, int, List[Point2D], int]]:
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
            if exclude_feat_id is not None and feat.id() == exclude_feat_id:
                continue

            geom = feat.geometry()
            if geom.isEmpty() or geom.type() != QgsWkbTypes.LineGeometry:
                continue

            sqr_d, min_pt, after_v, left_of = geom.closestSegmentWithContext(layer_pt)
            min_pt_canvas = self.to_canvas_point(layer, min_pt)
            d_canvas = math.hypot(canvas_pt.x() - min_pt_canvas.x(), canvas_pt.y() - min_pt_canvas.y())

            if d_canvas <= tol_canvas and d_canvas < best_dist:
                best_dist = d_canvas
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

    def _set_status_tip(self, text: str):
        if self.iface:
            self.iface.mainWindow().statusBar().showMessage(text, 2500)
