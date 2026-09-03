#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Narzędzie rysowania z Polar Trackingiem i przyciąganiem do kątów (CAD).
Autor: Mikołaj Sazonov
"""

import math
from typing import Optional, List, Tuple
from qgis.PyQt.QtCore import Qt, QPoint, QEvent
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import (
    QActionGroup,
    QWidgetAction,
    QMenu,
    QLabel,
    QAction
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
    QgsFeatureRequest,
    QgsCoordinateTransform,
    QgsProject,
    QgsSnappingConfig,
    Qgis,
    QgsMessageLog
)
from .base_curve_tool import BaseCurveTool
from ..gui.settings_widget import CurveSettingsWidget
from ..gui.polar_input_overlay import PolarInputOverlay
from ..gui.polar_settings_dialog import PolarSettingsDialog
from ..core.polar_state import (
    PolarState,
    PolarAngleMeasurement,
    POLAR_INCREMENT_PRESETS,
    format_preset_label
)
try:
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.i18n import tr
from ..core.geometry_utils import (
    vector_angle_deg,
    normalize_angle_deg,
    find_polar_snap_angle,
    project_point_on_ray_2d,
    ray_segment_intersection_2d,
    project_point_on_ray_t
)
from ..core.offset_utils import extract_rings_as_line
from ..core.layer_modifier import LayerModifier


class PolarDigitizeTool(BaseCurveTool):
    """
    Narzędzie mapowe do rysowania linii, polilinii i poligonów ze śledzeniem biegunowym (Polar Tracking).
    Umożliwia pełny snapping (wierzchołki, odcinki, środki, przecięcia), przyciąganie do kątów oraz wpisywanie długości z klawiatury.
    """

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget, iface=None):
        super().__init__(canvas, settings_widget)
        self.iface = iface
        self.state = PolarState.instance()

        # Punkty wprowadzone przez użytkownika w układzie współrzędnych aktywnej warstwy
        self.vertices: List[QgsPointXY] = []

        # Informacje o krawędzi początkowej (dla bazy kąta względnego)
        self.base_edge_points: Optional[Tuple[QgsPointXY, QgsPointXY]] = None
        self.base_angle: float = 0.0

        # Bieżące dane kursora i przyciągania
        self.current_snapped_pt: Optional[QgsPointXY] = None
        self.current_length: float = 0.0
        self.current_map_angle: float = 0.0
        self.current_rel_angle: Optional[float] = None
        self.is_polar_snapped: bool = False

        # Wskaźnik przyciągania QGIS
        self.snap_indicator = QgsSnapIndicator(self.canvas())

        # Pływający widget CAD
        self.overlay = PolarInputOverlay(self.canvas())
        self.overlay.distanceSubmitted.connect(self._on_distance_submitted)
        self.overlay.cancelled.connect(self._cancel_operation)

        # Gumki podglądu
        # 1. Szkic rysowanej geometrii (pomarańczowy/czerwony)
        self.sketch_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.sketch_band.setColor(QColor(245, 124, 0, 220))
        self.sketch_band.setWidth(2)

        # 2. Zielony promień Polar Tracking (CAD)
        self.tracking_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.tracking_band.setColor(QColor(0, 230, 118, 220))
        self.tracking_band.setWidth(1)
        self.tracking_band.setLineStyle(Qt.DashLine)

        # 3. Błękitne podświetlenie krawędzi początkowej (baza kąta)
        self.base_edge_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.base_edge_band.setColor(QColor(0, 229, 255, 230))
        self.base_edge_band.setWidth(3)

        # 4. Marker punktu przyciągania (gdy używamy wewnętrznego wyszukiwania)
        self.snap_point_band = QgsRubberBand(self.canvas(), QgsWkbTypes.PointGeometry)
        self.snap_point_band.setColor(QColor(255, 0, 128, 220))
        self.snap_point_band.setIcon(QgsRubberBand.ICON_BOX)
        self.snap_point_band.setIconSize(8)

    def activate(self):
        super().activate()
        self.canvas().installEventFilter(self)
        self.canvas().setFocus()
        if self.settings():
            self.settings().set_tool_mode('polar')

        # Automatyczne zapewnienie, że przyciąganie (Snapping) w projekcie jest aktywne
        cfg = QgsProject.instance().snappingConfig()
        if not cfg.enabled():
            cfg.setEnabled(True)
            cfg.setMode(QgsSnappingConfig.AllLayers)
            cfg.setTypeFlag(QgsSnappingConfig.VertexFlag | QgsSnappingConfig.SegmentFlag | QgsSnappingConfig.MiddleOfSegmentFlag)
            cfg.setIntersectionSnapping(True)
            QgsProject.instance().setSnappingConfig(cfg)
            self.canvas().snappingUtils().setConfig(cfg)

    def deactivate(self):
        try:
            self.canvas().removeEventFilter(self)
        except Exception as err:
            QgsMessageLog.logMessage(f"Event filter cleanup: {err}", "MSA: CurveMaster", Qgis.Info)
        self._cancel_operation()
        super().deactivate()

    def eventFilter(self, obj, event):
        if obj == self.canvas() and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                if len(self.vertices) > 0 and self.overlay.isVisible():
                    self.overlay._on_submit()
                self.canvas().setFocus()
                return True
        return super().eventFilter(obj, event)

    def create_dropdown_menu(self, parent=None) -> QMenu:
        """Tworzy rozwijane menu dla przycisku Polar Tracking na pasku narzędzi."""
        menu = QMenu(parent or self.canvas())
        menu.setTitle(tr("Polar Tracking Settings", "Ustawienia śledzenia biegunowego"))

        # 1. Włącz/wyłącz
        act_toggle = menu.addAction(tr("Polar Tracking On", "Śledzenie biegunowe (Włącz)"))
        act_toggle.setCheckable(True)
        act_toggle.setChecked(self.state.enabled)
        act_toggle.toggled.connect(lambda chk: setattr(self.state, 'enabled', chk))

        menu.addSeparator()

        # 2. Podmenu kroków kątowych
        menu_inc = menu.addMenu(tr("Increment angle", "Krok kąta"))
        group_inc = QActionGroup(menu_inc)
        group_inc.setExclusive(True)

        for step in POLAR_INCREMENT_PRESETS:
            lbl = format_preset_label(step)
            act_inc = menu_inc.addAction(lbl)
            act_inc.setCheckable(True)
            act_inc.setChecked(abs(self.state.increment_angle - step) < 1e-4)
            group_inc.addAction(act_inc)

            def make_inc_handler(s=step):
                return lambda: setattr(self.state, 'increment_angle', s)
            act_inc.triggered.connect(make_inc_handler(step))

        # 3. Baza pomiaru (Measurement)
        menu_base = menu.addMenu(tr("Angle measurement", "Pomiar kąta"))
        group_base = QActionGroup(menu_base)
        group_base.setExclusive(True)

        act_rel = menu_base.addAction(tr("Relative (to previous segment / starting edge)", "Kąt względny (do poprzedniego segmentu / krawędzi)"))
        act_rel.setCheckable(True)
        act_rel.setChecked(self.state.measurement_mode == PolarAngleMeasurement.RELATIVE)
        act_rel.triggered.connect(lambda: setattr(self.state, 'measurement_mode', PolarAngleMeasurement.RELATIVE))
        group_base.addAction(act_rel)

        act_abs = menu_base.addAction(tr("Absolute (to coordinate system)", "Kąt bezwzględny (do układu współrzędnych)"))
        act_abs.setCheckable(True)
        act_abs.setChecked(self.state.measurement_mode == PolarAngleMeasurement.ABSOLUTE)
        act_abs.triggered.connect(lambda: setattr(self.state, 'measurement_mode', PolarAngleMeasurement.ABSOLUTE))
        group_base.addAction(act_abs)

        menu.addSeparator()

        # 4. Podmenu ustawień przyciągania (Snapping)
        menu_snap = menu.addMenu(tr("Snapping", "Przyciąganie (Snapping)"))
        self._build_snapping_submenu(menu_snap)

        menu.addSeparator()

        # 5. Okno ustawień zaawansowanych
        act_dialog = menu.addAction(tr("Polar Tracking CAD Settings...", "Ustawienia śledzenia biegunowego (CAD)..."))
        act_dialog.triggered.connect(self._open_settings_dialog)

        return menu

    def _build_snapping_submenu(self, menu_snap: QMenu):
        """Buduje zwięzłe podmenu konfiguracji przyciągania bezpośrednio w menu wtyczki."""
        cfg = QgsProject.instance().snappingConfig()

        act_snap_toggle = menu_snap.addAction(tr("Enable Snapping", "Włącz przyciąganie"))
        act_snap_toggle.setCheckable(True)
        act_snap_toggle.setChecked(cfg.enabled())

        def toggle_snap(chk):
            c = QgsProject.instance().snappingConfig()
            c.setEnabled(chk)
            QgsProject.instance().setSnappingConfig(c)
            self.canvas().snappingUtils().setConfig(c)
        act_snap_toggle.toggled.connect(toggle_snap)

        menu_snap.addSeparator()

        # Zakres warstw
        menu_layers = menu_snap.addMenu(tr("Layer scope", "Zakres warstw"))
        grp_layers = QActionGroup(menu_layers)
        grp_layers.setExclusive(True)

        act_all = menu_layers.addAction(tr("All layers", "Wszystkie warstwy"))
        act_all.setCheckable(True)
        act_all.setChecked(cfg.mode() == QgsSnappingConfig.AllLayers)

        def set_all_layers():
            c = QgsProject.instance().snappingConfig()
            c.setMode(QgsSnappingConfig.AllLayers)
            QgsProject.instance().setSnappingConfig(c)
            self.canvas().snappingUtils().setConfig(c)
        act_all.triggered.connect(set_all_layers)
        grp_layers.addAction(act_all)

        act_act = menu_layers.addAction(tr("Active layer only", "Tylko aktywna warstwa"))
        act_act.setCheckable(True)
        act_act.setChecked(cfg.mode() == QgsSnappingConfig.ActiveLayer)

        def set_active_layer():
            c = QgsProject.instance().snappingConfig()
            c.setMode(QgsSnappingConfig.ActiveLayer)
            QgsProject.instance().setSnappingConfig(c)
            self.canvas().snappingUtils().setConfig(c)
        act_act.triggered.connect(set_active_layer)
        grp_layers.addAction(act_act)

        # Typy obiektów przyciągania
        menu_types = menu_snap.addMenu(tr("Snap to", "Przyciągaj do"))

        def update_type_flag(flag, enabled):
            c = QgsProject.instance().snappingConfig()
            cur = c.typeFlag()
            if enabled:
                c.setTypeFlag(cur | flag)
            else:
                c.setTypeFlag(cur & ~flag)
            QgsProject.instance().setSnappingConfig(c)
            self.canvas().snappingUtils().setConfig(c)

        act_v = menu_types.addAction(tr("Vertices", "Wierzchołków"))
        act_v.setCheckable(True)
        act_v.setChecked(bool(cfg.typeFlag() & QgsSnappingConfig.VertexFlag))
        act_v.toggled.connect(lambda chk: update_type_flag(QgsSnappingConfig.VertexFlag, chk))

        act_s = menu_types.addAction(tr("Segments / Edges", "Krawędzi / Odcinków"))
        act_s.setCheckable(True)
        act_s.setChecked(bool(cfg.typeFlag() & QgsSnappingConfig.SegmentFlag))
        act_s.toggled.connect(lambda chk: update_type_flag(QgsSnappingConfig.SegmentFlag, chk))

        act_m = menu_types.addAction(tr("Segment midpoints", "Środków odcinków"))
        act_m.setCheckable(True)
        act_m.setChecked(bool(cfg.typeFlag() & QgsSnappingConfig.MiddleOfSegmentFlag))
        act_m.toggled.connect(lambda chk: update_type_flag(QgsSnappingConfig.MiddleOfSegmentFlag, chk))

        act_i = menu_types.addAction(tr("Intersections", "Przecięć"))
        act_i.setCheckable(True)
        act_i.setChecked(cfg.intersectionSnapping())

        def toggle_intersections(chk):
            c = QgsProject.instance().snappingConfig()
            c.setIntersectionSnapping(chk)
            QgsProject.instance().setSnappingConfig(c)
            self.canvas().snappingUtils().setConfig(c)
        act_i.toggled.connect(toggle_intersections)

    def _open_settings_dialog(self):
        dlg = PolarSettingsDialog(self.canvas())
        dlg.exec_()

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        active_layer = self.active_editable_layer()
        canvas_pt = e.mapPoint()
        layer_pt = self.to_layer_point(active_layer, canvas_pt) if active_layer else canvas_pt

        # 1. Sprawdzenie przyciągania QGIS
        match = self.canvas().snappingUtils().snapToMap(e.pos())
        has_qgis_snap = match.isValid()

        # FAZA 1: Brak postawionych punktów (oczekiwanie na V0)
        if len(self.vertices) == 0:
            if has_qgis_snap:
                self.snap_indicator.setMatch(match)
                self.snap_indicator.setVisible(True)
                self.snap_point_band.reset(QgsWkbTypes.PointGeometry)

                snapped_canvas_pt = match.point()
                snapped_layer_pt = self.to_layer_point(active_layer, snapped_canvas_pt)
                self.current_snapped_pt = snapped_layer_pt

                if match.hasEdge():
                    p1, p2 = match.edgePoints()
                    p1_l = self.to_layer_point(active_layer, p1)
                    p2_l = self.to_layer_point(active_layer, p2)
                    self.base_edge_points = (p1_l, p2_l)
                    self.base_angle = vector_angle_deg((p1_l.x(), p1_l.y()), (p2_l.x(), p2_l.y()))

                    # Podświetl krawędź
                    p1_c = self.to_canvas_point(active_layer, p1_l)
                    p2_c = self.to_canvas_point(active_layer, p2_l)
                    geom_edge = QgsGeometry.fromPolylineXY([p1_c, p2_c])
                    self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
                    self.base_edge_band.setToGeometry(geom_edge, None)
                else:
                    # Sprawdź czy punkt leży na jakiejś krawędzi dla zablokowania bazy kątowej
                    edge_res = self._find_edge_near(snapped_canvas_pt)
                    if edge_res:
                        pa_t, pb_t, _, _ = edge_res
                        self.base_edge_points = (pa_t, pb_t)
                        self.base_angle = vector_angle_deg((pa_t.x(), pa_t.y()), (pb_t.x(), pb_t.y()))
                        geom_edge = QgsGeometry.fromPolylineXY([self.to_canvas_point(active_layer, pa_t), self.to_canvas_point(active_layer, pb_t)])
                        self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
                        self.base_edge_band.setToGeometry(geom_edge, None)
                    else:
                        self.base_edge_points = None
                        self.base_angle = 0.0
                        self.base_edge_band.reset(QgsWkbTypes.LineGeometry)

                self._set_status_tip(f"MSA Polar: Przyciągnięto [QGIS Snap] (Baza 0° = {self.base_angle:.1f}°)")
                return

            # Fallback: Wewnętrzne wyszukiwanie krawędzi i punktów jeśli snapping w QGIS jest wyłączony
            edge_res = self._find_edge_near(canvas_pt)
            if edge_res:
                self.snap_indicator.setVisible(False)
                pa_t, pb_t, pt_snap_l, snap_type = edge_res
                self.base_edge_points = (pa_t, pb_t)
                self.base_angle = vector_angle_deg((pa_t.x(), pa_t.y()), (pb_t.x(), pb_t.y()))
                self.current_snapped_pt = pt_snap_l

                # Podświetlenie krawędzi na błękitno
                geom_edge = QgsGeometry.fromPolylineXY([self.to_canvas_point(active_layer, pa_t), self.to_canvas_point(active_layer, pb_t)])
                self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
                self.base_edge_band.setToGeometry(geom_edge, None)

                # Wskaźnik punktu przyciągnięcia
                pt_snap_c = self.to_canvas_point(active_layer, pt_snap_l)
                self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
                self.snap_point_band.addPoint(pt_snap_c)

                self._set_status_tip(f"MSA Polar: Przyciągnięto do [{snap_type}] (Baza 0° = {self.base_angle:.1f}°)")
            else:
                self.base_edge_points = None
                self.base_angle = 0.0
                self.current_snapped_pt = None
                self.snap_indicator.setVisible(False)
                self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
                self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
                if not active_layer:
                    self._set_status_tip("MSA Polar: Wybierz warstwę liniową lub poligonową i włącz tryb edycji.")
                else:
                    self._set_status_tip("MSA Polar: Kliknij punkt początkowy (najedź na krawędź lub wierzchołek).")
            return

        # FAZA 2: Rysowanie kolejnych segmentów (V1, V2, ...)
        last_v = self.vertices[-1]
        raw_dist = math.hypot(layer_pt.x() - last_v.x(), layer_pt.y() - last_v.y())
        raw_angle = vector_angle_deg((last_v.x(), last_v.y()), (layer_pt.x(), layer_pt.y()))

        # Ustalenie bazy kątowej
        if self.state.measurement_mode == PolarAngleMeasurement.RELATIVE:
            if len(self.vertices) == 1:
                effective_base_angle = self.base_angle
            else:
                prev_v = self.vertices[-2]
                effective_base_angle = vector_angle_deg((prev_v.x(), prev_v.y()), (last_v.x(), last_v.y()))
        else:
            effective_base_angle = 0.0

        # Sprawdzenie przyciągania do kąta
        snap_res = None
        if self.state.enabled and raw_dist > 1e-4:
            active_add_angles = self.state.get_active_additional_angles()
            snap_res = find_polar_snap_angle(
                current_angle_deg=raw_angle,
                base_angle_deg=effective_base_angle,
                increment_deg=self.state.increment_angle,
                additional_angles=active_add_angles,
                tolerance_deg=self.state.tolerance_deg
            )

        if snap_res is not None:
            snapped_map_angle, snapped_rel_angle = snap_res
            self.is_polar_snapped = True

            # Sprawdzenie jednoczesnego przyciągania: kąt polarny + przecięcie z istniejącą krawędzią / wierzchołek
            ray_snap = self._find_ray_snap(last_v, snapped_map_angle, canvas_pt, active_layer)
            if ray_snap is not None:
                eff_dist, snapped_pt, edge_pts, snap_label = ray_snap
                self.current_snapped_pt = snapped_pt
                self.current_length = eff_dist
                self.current_map_angle = snapped_map_angle
                self.current_rel_angle = snapped_rel_angle

                # Podświetlenie przecinanej krawędzi
                if edge_pts:
                    p1_t, p2_t = edge_pts
                    p1_c = self.to_canvas_point(active_layer, p1_t)
                    p2_c = self.to_canvas_point(active_layer, p2_t)
                    geom_edge = QgsGeometry.fromPolylineXY([p1_c, p2_c])
                    self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
                    self.base_edge_band.setToGeometry(geom_edge, None)
                else:
                    self.base_edge_band.reset(QgsWkbTypes.LineGeometry)

                # Wskaźnik punktu przecięcia
                pt_snap_c = self.to_canvas_point(active_layer, snapped_pt)
                self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
                self.snap_point_band.addPoint(pt_snap_c)
                self.snap_indicator.setVisible(False)

                badge = f"Polar: {snapped_rel_angle:.1f}° | {snap_label}"
                self.overlay.update_info(eff_dist, snapped_map_angle, snapped_rel_angle, is_polar_snapped=True, badge_text=badge)
                self._set_status_tip(f"MSA Polar: Przyciągnięto do kąta {snapped_map_angle:.1f}° i [{snap_label}] (Dł = {eff_dist:.2f} m). Enter/Tab/Lewoklik = zatwierdź.")
            else:
                self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
                self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
                self.snap_indicator.setVisible(False)

                px, py = project_point_on_ray_2d((last_v.x(), last_v.y()), raw_dist, snapped_map_angle)
                snapped_pt = QgsPointXY(px, py)
                self.current_snapped_pt = snapped_pt
                self.current_length = raw_dist
                self.current_map_angle = snapped_map_angle
                self.current_rel_angle = snapped_rel_angle

                # Aktualizacja okienka CAD
                self.overlay.update_info(raw_dist, snapped_map_angle, snapped_rel_angle, is_polar_snapped=True)
                self._set_status_tip(f"MSA Polar: Dł = {raw_dist:.2f} m, Kąt = {snapped_map_angle:.1f}° [Polar {snapped_rel_angle:.1f}°]. Enter/Tab = wpisz dł.")

            # Rysowanie zielonego promienia polarnego
            ray_length = max(self.current_length * 1.5, self._canvas.mapUnitsPerPixel() * 1500.0)
            r_px, r_py = project_point_on_ray_2d((last_v.x(), last_v.y()), ray_length, snapped_map_angle)
            ray_geom = QgsGeometry.fromPolylineXY([
                self.to_canvas_point(active_layer, last_v),
                self.to_canvas_point(active_layer, QgsPointXY(r_px, r_py))
            ])
            self.tracking_band.reset(QgsWkbTypes.LineGeometry)
            self.tracking_band.setToGeometry(ray_geom, None)
        else:
            self.is_polar_snapped = False
            if has_qgis_snap:
                self.snap_indicator.setMatch(match)
                self.snap_indicator.setVisible(True)
                snapped_pt = self.to_layer_point(active_layer, match.point())
                self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
            else:
                self.snap_indicator.setVisible(False)
                edge_res = self._find_edge_near(canvas_pt)
                if edge_res:
                    _, _, pt_snap_l, snap_type = edge_res
                    snapped_pt = pt_snap_l
                    self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
                    self.snap_point_band.addPoint(self.to_canvas_point(active_layer, pt_snap_l))
                else:
                    snapped_pt = layer_pt
                    self.snap_point_band.reset(QgsWkbTypes.PointGeometry)

            self.current_snapped_pt = snapped_pt
            calc_dist = math.hypot(snapped_pt.x() - last_v.x(), snapped_pt.y() - last_v.y())
            calc_angle = vector_angle_deg((last_v.x(), last_v.y()), (snapped_pt.x(), snapped_pt.y()))
            self.current_length = calc_dist
            self.current_map_angle = calc_angle
            self.current_rel_angle = normalize_angle_deg(calc_angle - effective_base_angle)

            self.tracking_band.reset(QgsWkbTypes.LineGeometry)
            self.overlay.update_info(calc_dist, calc_angle, self.current_rel_angle, is_polar_snapped=False)
            self._set_status_tip(f"MSA Polar: Dł = {calc_dist:.2f} m, Kąt = {calc_angle:.1f}°. Lewoklik = wierzchołek, Prawoklik = zakończ.")

        # Aktualizacja szkicu geometrii
        self._update_sketch_band(snapped_pt, active_layer)

        # Aktualizacja pozycji okienka CAD
        self.overlay.update_position(e.pos(), self.canvas().rect())
        self.overlay.show()

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.RightButton:
            self._commit_geometry()
            return

        if e.button() != Qt.LeftButton:
            return

        active_layer = self.active_editable_layer()
        if not active_layer:
            if self.iface:
                self.iface.messageBar().pushWarning(
                    "MSA: CurveMaster",
                    "Wybierz warstwę liniową lub poligonową i włącz tryb edycji, aby rysować."
                )
            return

        canvas_pt = e.mapPoint()
        layer_pt = self.to_layer_point(active_layer, canvas_pt)

        # FAZA 1: Dodanie punktu startowego V0 (Z PRECYZYJNYM SNAPPEM!)
        if len(self.vertices) == 0:
            start_pt = self.current_snapped_pt if self.current_snapped_pt is not None else layer_pt
            self.vertices.append(start_pt)
            self.snap_indicator.setVisible(False)
            self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
            self.overlay.update_position(e.pos(), self.canvas().rect())
            self.overlay.show()
            self.canvas().setFocus()
            return

        # FAZA 2: Dodanie kolejnego punktu
        pt_to_add = self.current_snapped_pt if self.current_snapped_pt is not None else layer_pt
        self.vertices.append(pt_to_add)
        self.snap_indicator.setVisible(False)
        self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
        self.canvas().setFocus()

    def _on_distance_submitted(self, distance_val: float):
        """Użytkownik wpisał odległość w okienku CAD i zatwierdził Enter/Tab."""
        if len(self.vertices) == 0:
            return

        last_v = self.vertices[-1]
        target_angle = self.current_map_angle

        # Odmierzamy odległość wzdłuż przyciągniętego lub bieżącego kąta
        px, py = project_point_on_ray_2d((last_v.x(), last_v.y()), distance_val, target_angle)
        new_pt = QgsPointXY(px, py)
        self.vertices.append(new_pt)

        active_layer = self.active_editable_layer()
        self._update_sketch_band(new_pt, active_layer)
        self.canvas().setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel_operation()
            return

        if e.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            if len(self.vertices) > 0:
                self.vertices.pop()
                if len(self.vertices) == 0:
                    self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
                    self.tracking_band.reset(QgsWkbTypes.LineGeometry)
                    self.sketch_band.reset(QgsWkbTypes.LineGeometry)
                    self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
                    self.snap_indicator.setVisible(False)
                    self.overlay.hide()
                else:
                    active_layer = self.active_editable_layer()
                    self._update_sketch_band(self.vertices[-1], active_layer)
                self._set_status_tip("MSA Polar: Cofnięto ostatni wierzchołek.")
            return

        if len(self.vertices) > 0:
            key_text = e.text()
            if key_text and (key_text.isdigit() or key_text in ('.', ',')):
                self.overlay.activate_with_text(key_text)
                return
            elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._commit_geometry()
                return

        super().keyPressEvent(e)

    def _update_sketch_band(self, current_cursor_pt: QgsPointXY, active_layer: Optional[QgsVectorLayer]):
        """Rysuje dotychczasowe wierzchołki oraz odcinek do bieżącego kursora."""
        if len(self.vertices) == 0:
            self.sketch_band.reset(QgsWkbTypes.LineGeometry)
            return

        pts_canvas = [self.to_canvas_point(active_layer, v) for v in self.vertices]
        pts_canvas.append(self.to_canvas_point(active_layer, current_cursor_pt))

        is_poly = active_layer and active_layer.geometryType() == QgsWkbTypes.PolygonGeometry

        if is_poly and len(pts_canvas) >= 3:
            geom = QgsGeometry.fromPolygonXY([pts_canvas + [pts_canvas[0]]])
            self.sketch_band.reset(QgsWkbTypes.PolygonGeometry)
        else:
            geom = QgsGeometry.fromPolylineXY(pts_canvas)
            self.sketch_band.reset(QgsWkbTypes.LineGeometry)

        self.sketch_band.setToGeometry(geom, None)

    def _commit_geometry(self):
        """Zatwierdza gotowy obiekt i wstawia go do aktywnej edytowalnej warstwy."""
        active_layer = self.active_editable_layer()
        if not active_layer:
            self._cancel_operation()
            return

        is_poly = (active_layer.geometryType() == QgsWkbTypes.PolygonGeometry)
        min_pts = 3 if is_poly else 2

        if len(self.vertices) < min_pts:
            if self.iface:
                self.iface.messageBar().pushWarning(
                    "MSA: CurveMaster",
                    f"Zbyt mało punktów do utworzenia obiektu (wymagane min. {min_pts})."
                )
            self._cancel_operation()
            return

        if is_poly:
            ring = list(self.vertices)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            geom = QgsGeometry.fromPolygonXY([ring])
            cmd_name = "MSA: Rysuj poligon z Polar Trackingiem"
        else:
            geom = QgsGeometry.fromPolylineXY(self.vertices)
            cmd_name = "MSA: Rysuj polilinię z Polar Trackingiem"

        feat_id = LayerModifier.add_feature(active_layer, geom, cmd_name)
        if feat_id is not None and self.iface:
            self.iface.messageBar().pushInfo(
                "MSA: CurveMaster",
                f"Utworzono nowy obiekt ({'poligon' if is_poly else 'polilinia'}) z Polar Trackingiem."
            )

        self._cancel_operation()

    def _cancel_operation(self):
        """Resetuje stan narzędzia do oczekiwania."""
        self.vertices.clear()
        self.base_edge_points = None
        self.base_angle = 0.0
        self.current_snapped_pt = None
        self.current_length = 0.0
        self.current_map_angle = 0.0
        self.current_rel_angle = None
        self.is_polar_snapped = False

        self.sketch_band.reset(QgsWkbTypes.LineGeometry)
        self.tracking_band.reset(QgsWkbTypes.LineGeometry)
        self.base_edge_band.reset(QgsWkbTypes.LineGeometry)
        self.snap_point_band.reset(QgsWkbTypes.PointGeometry)
        self.snap_indicator.setVisible(False)
        if self.overlay:
            self.overlay.hide()
            self.overlay.edit.clear()

        self.canvas().setFocus()

    def _find_ray_snap(
        self,
        last_v: QgsPointXY,
        ray_angle_deg: float,
        canvas_point: QgsPointXY,
        active_layer: Optional[QgsVectorLayer]
    ) -> Optional[Tuple[float, QgsPointXY, Optional[Tuple[QgsPointXY, QgsPointXY]], str]]:
        """
        Sprawdza czy promień polarny (last_v, ray_angle_deg) przecina istniejącą krawędź
        bądź pokrywa się z wierzchołkiem w pobliżu kursora.
        Zwraca: (odległość_wzdłuż_promienia_t, punkt_snapu_w_layer_crs, punkty_krawędzi_lub_None, opis_snapu)
        """
        target_crs = active_layer.crs() if active_layer else self._canvas.mapSettings().destinationCrs()
        mupp = self._canvas.mapUnitsPerPixel()
        tol_canvas = mupp * 22.0

        search_rect_canvas = QgsRectangle(
            canvas_point.x() - tol_canvas,
            canvas_point.y() - tol_canvas,
            canvas_point.x() + tol_canvas,
            canvas_point.y() + tol_canvas
        )

        layers_to_check: List[QgsVectorLayer] = []
        if active_layer:
            layers_to_check.append(active_layer)
        for lyr in self._canvas.layers():
            if isinstance(lyr, QgsVectorLayer) and lyr != active_layer:
                if lyr.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                    layers_to_check.append(lyr)

        best_cursor_dist = float('inf')
        best_snap = None
        origin_tuple = (last_v.x(), last_v.y())

        for lyr in layers_to_check:
            search_rect_lyr = self.to_layer_rect(lyr, search_rect_canvas)
            req = QgsFeatureRequest().setFilterRect(search_rect_lyr).setFlags(QgsFeatureRequest.ExactIntersect)

            for feat in lyr.getFeatures(req):
                geom = feat.geometry()
                if geom.isEmpty():
                    continue

                is_poly = (geom.type() == QgsWkbTypes.PolygonGeometry)
                boundary = extract_rings_as_line(geom) if is_poly else geom
                if boundary.isEmpty():
                    continue

                lines = boundary.asMultiPolyline() if boundary.isMultipart() else [boundary.asPolyline()]
                for line in lines:
                    for i in range(len(line) - 1):
                        p_a = line[i]
                        p_b = line[i + 1]

                        pa_t = self._transform_point_to_crs(QgsPointXY(p_a), lyr.crs(), target_crs)
                        pb_t = self._transform_point_to_crs(QgsPointXY(p_b), lyr.crs(), target_crs)

                        # 1. Sprawdzenie przecięcia promienia polarnego z odcinkiem
                        inter = ray_segment_intersection_2d(
                            origin_tuple,
                            ray_angle_deg,
                            (pa_t.x(), pa_t.y()),
                            (pb_t.x(), pb_t.y())
                        )
                        if inter is not None:
                            t_int, (ix, iy) = inter
                            pt_int_lyr = QgsPointXY(ix, iy)
                            pt_int_canvas = self.to_canvas_point(active_layer, pt_int_lyr)
                            dist_to_cursor = math.hypot(canvas_point.x() - pt_int_canvas.x(), canvas_point.y() - pt_int_canvas.y())

                            if dist_to_cursor <= tol_canvas and dist_to_cursor < best_cursor_dist:
                                best_cursor_dist = dist_to_cursor
                                best_snap = (t_int, pt_int_lyr, (pa_t, pb_t), "Przecięcie z krawędzią")

                        # 2. Sprawdzenie wierzchołka leżącego na linii promienia
                        t_v, perp_dist, (proj_x, proj_y) = project_point_on_ray_t(
                            origin_tuple,
                            ray_angle_deg,
                            (pa_t.x(), pa_t.y())
                        )
                        if t_v > 1e-4:
                            pt_proj_lyr = QgsPointXY(proj_x, proj_y)
                            pt_proj_canvas = self.to_canvas_point(active_layer, pt_proj_lyr)
                            dist_to_cursor_v = math.hypot(canvas_point.x() - pt_proj_canvas.x(), canvas_point.y() - pt_proj_canvas.y())
                            pa_canvas = self.to_canvas_point(active_layer, pa_t)
                            perp_canvas = math.hypot(pa_canvas.x() - pt_proj_canvas.x(), pa_canvas.y() - pt_proj_canvas.y())

                            if perp_canvas <= tol_canvas and dist_to_cursor_v <= tol_canvas and dist_to_cursor_v < best_cursor_dist:
                                best_cursor_dist = dist_to_cursor_v
                                best_snap = (t_v, pt_proj_lyr, None, "Wierzchołek na promieniu")

        return best_snap

    def _find_edge_near(self, canvas_point: QgsPointXY) -> Optional[Tuple[QgsPointXY, QgsPointXY, QgsPointXY, str]]:
        """
        Wyszukuje najbliższy segment/krawędź i wyznacza punkt przyciągania (wierzchołek, środek, krawędź).
        Zwraca: (pa_in_layer_crs, pb_in_layer_crs, snapped_point_in_layer_crs, snap_type_str)
        """
        active_layer = self.active_editable_layer()
        target_crs = active_layer.crs() if active_layer else self._canvas.mapSettings().destinationCrs()

        mupp = self._canvas.mapUnitsPerPixel()
        tol_canvas = mupp * 18.0  # 18 px tolerancji

        search_rect_canvas = QgsRectangle(
            canvas_point.x() - tol_canvas,
            canvas_point.y() - tol_canvas,
            canvas_point.x() + tol_canvas,
            canvas_point.y() + tol_canvas
        )

        layers_to_check: List[QgsVectorLayer] = []
        if active_layer:
            layers_to_check.append(active_layer)
        for lyr in self._canvas.layers():
            if isinstance(lyr, QgsVectorLayer) and lyr != active_layer:
                if lyr.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                    layers_to_check.append(lyr)

        best_dist = float('inf')
        best_res: Optional[Tuple[QgsPointXY, QgsPointXY, QgsPointXY, str]] = None

        for lyr in layers_to_check:
            search_rect_lyr = self.to_layer_rect(lyr, search_rect_canvas)
            req = QgsFeatureRequest().setFilterRect(search_rect_lyr).setFlags(QgsFeatureRequest.ExactIntersect)

            for feat in lyr.getFeatures(req):
                geom = feat.geometry()
                if geom.isEmpty():
                    continue

                is_poly = (geom.type() == QgsWkbTypes.PolygonGeometry)
                boundary = extract_rings_as_line(geom) if is_poly else geom
                if boundary.isEmpty():
                    continue

                pt_in_lyr = self.to_layer_point(lyr, canvas_point)
                sqr_dist, min_pt, after_vertex, left_of = boundary.closestSegmentWithContext(pt_in_lyr)
                min_pt_c = self.to_canvas_point(lyr, min_pt)
                dist_c = math.hypot(canvas_point.x() - min_pt_c.x(), canvas_point.y() - min_pt_c.y())

                if dist_c <= tol_canvas and dist_c < best_dist:
                    start_v_nr = after_vertex - 1
                    end_v_nr = after_vertex
                    if start_v_nr >= 0:
                        p_a = boundary.vertexAt(start_v_nr)
                        p_b = boundary.vertexAt(end_v_nr)

                        # Punkty krawędzi w canvas
                        pa_c = self.to_canvas_point(lyr, p_a)
                        pb_c = self.to_canvas_point(lyr, p_b)
                        pmid_c = QgsPointXY((pa_c.x() + pb_c.x()) / 2.0, (pa_c.y() + pb_c.y()) / 2.0)

                        dist_pa = math.hypot(canvas_point.x() - pa_c.x(), canvas_point.y() - pa_c.y())
                        dist_pb = math.hypot(canvas_point.x() - pb_c.x(), canvas_point.y() - pb_c.y())
                        dist_pmid = math.hypot(canvas_point.x() - pmid_c.x(), canvas_point.y() - pmid_c.y())

                        vertex_tol = tol_canvas * 0.7
                        if dist_pa <= vertex_tol:
                            chosen_snap_lyr = QgsPointXY(p_a)
                            snap_type = "Wierzchołek"
                        elif dist_pb <= vertex_tol:
                            chosen_snap_lyr = QgsPointXY(p_b)
                            snap_type = "Wierzchołek"
                        elif dist_pmid <= vertex_tol:
                            chosen_snap_lyr = QgsPointXY((p_a.x() + p_b.x()) / 2.0, (p_a.y() + p_b.y()) / 2.0)
                            snap_type = "Środek odcinka"
                        else:
                            chosen_snap_lyr = min_pt
                            snap_type = "Krawędź"

                        pa_t = self._transform_point_to_crs(QgsPointXY(p_a), lyr.crs(), target_crs)
                        pb_t = self._transform_point_to_crs(QgsPointXY(p_b), lyr.crs(), target_crs)
                        snap_t = self._transform_point_to_crs(chosen_snap_lyr, lyr.crs(), target_crs)

                        best_dist = dist_c
                        best_res = (pa_t, pb_t, snap_t, snap_type)

        return best_res

    def _transform_point_to_crs(self, pt: QgsPointXY, src_crs, dst_crs) -> QgsPointXY:
        if not src_crs.isValid() or not dst_crs.isValid() or src_crs == dst_crs:
            return pt
        try:
            trans = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
            return trans.transform(pt)
        except Exception:
            return pt

    def _set_status_tip(self, text: str):
        if self.iface:
            self.iface.mainWindow().statusBar().showMessage(text, 3000)
