#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
***************************************************************************
*   MSA: CurveMaster - Narzędzie wylewania nawierzchni (Smart Pour).      *
*   Autor: Mikołaj Sazonov                                                *
***************************************************************************
"""

import math
from enum import Enum
from typing import Optional, List, Set, Dict
from qgis.PyQt.QtCore import Qt, QPoint, QEvent, QVariant
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import (
    QInputDialog,
    QLineEdit,
    QMenu,
    QActionGroup,
    QWidgetAction,
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
    QgsField,
    Qgis,
    QgsMessageLog
)
from .base_curve_tool import BaseCurveTool
from ..gui.settings_widget import CurveSettingsWidget
from ..gui.pour_input_overlay import PourInputOverlay
from ..core.pavement_pour_utils import (
    find_category_field_name,
    get_layer_unique_categories,
    compute_pour_polygon,
    merge_polygon_with_category,
    CategoryStyleInfo,
    get_layer_category_styles,
    find_category_style
)
try:
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.i18n import tr


class PourBoundaryScope(Enum):
    """Zakres warstw stanowiących krawędzie dla Smart Pour."""
    CUSTOM_LAYERS = "custom"         # Tylko wybrane przez użytkownika warstwy krawędzi
    VISIBLE_LINES = "visible_lines" # Wszystkie widoczne warstwy liniowe


class PavementPourTool(BaseCurveTool):
    """
    Narzędzie mapowe CAD Smart Pour do interaktywnego, stopniowego wylewania nawierzchni
    (chodniki, jezdnie, DDR, trawniki) w skali 1:500.
    Obsługuje dynamiczny promień odcięcia, zmianę kategorii w locie (klawisz Tab)
    oraz automatyczne scalanie (Auto-Merge) sąsiadujących nawierzchni tego samego typu.
    """

    STATE_IDLE = 0
    STATE_POURING = 1

    last_used_category: Optional[str] = None
    last_used_radius: float = 50.0

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget, iface=None):
        super().__init__(canvas, settings_widget)
        self.iface = iface
        self.state = self.STATE_IDLE

        # Pływający widget CAD HUD
        self.overlay = PourInputOverlay(self.canvas())
        self.overlay.radiusSubmitted.connect(self._on_overlay_radius_submitted)
        self.overlay.categoryCycleRequested.connect(lambda: self._cycle_category(1))
        self.overlay.categoryCyclePrevRequested.connect(lambda: self._cycle_category(-1))
        self.overlay.cancelled.connect(self._cancel_operation)

        # Gumka podglądu wylewanego poligonu (półprzezroczysty błękit/akcent)
        self.preview_band = QgsRubberBand(self.canvas(), QgsWkbTypes.PolygonGeometry)
        self.preview_band.setColor(QColor(13, 110, 253, 90))
        self.preview_band.setStrokeColor(QColor(13, 110, 253, 220))
        self.preview_band.setWidth(2)

        # Gumka pomocnicza linii promienia (od P0 do kursora)
        self.guide_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.guide_band.setColor(QColor(255, 150, 0, 180))
        self.guide_band.setWidth(1)

        # Gumka punktu początkowego P0
        self.start_pt_band = QgsRubberBand(self.canvas(), QgsWkbTypes.PointGeometry)
        self.start_pt_band.setColor(QColor(13, 110, 253, 230))
        self.start_pt_band.setIcon(QgsRubberBand.ICON_CIRCLE)
        self.start_pt_band.setIconSize(8)

        # Stan operacji
        self.start_canvas_pt: Optional[QgsPointXY] = None
        self.start_layer_pt: Optional[QgsPointXY] = None
        self.current_radius: float = self.last_used_radius
        self.current_poly_geom: Optional[QgsGeometry] = None
        self.active_categories: List[str] = []
        self.current_category_idx: int = 0
        self.cached_boundary_lines: List[QgsGeometry] = []
        self.cached_boundary_radius: float = 0.0
        self.category_styles: Dict[str, CategoryStyleInfo] = {}
        self._connected_style_layer: Optional[QgsVectorLayer] = None

        # Zakres warstw krawędzi (bariery)
        self.selected_boundary_layer_ids: Set[str] = set()
        self.include_active_layer_boundaries: bool = True
        self.boundary_scope: PourBoundaryScope = PourBoundaryScope.CUSTOM_LAYERS
        self._load_boundary_settings()

        # Synchronizacja ze zmianą w pasku ustawień
        self.settings_widget.pourCategoryChanged.connect(self._on_settings_category_changed)
        self.settings_widget.pourLayersDialogRequested.connect(self.open_boundary_layers_dialog)

    def _load_boundary_settings(self):
        """Wczytuje zapamiętane w projekcie ID warstw krawędzi."""
        project = QgsProject.instance()
        layer_ids, ok = project.readListEntry("MSACurveMaster", "PourBoundaryLayerIds")
        if ok and layer_ids:
            self.selected_boundary_layer_ids = set(layer_ids)
            self.boundary_scope = PourBoundaryScope.CUSTOM_LAYERS
        else:
            self.selected_boundary_layer_ids = set()
            self.boundary_scope = PourBoundaryScope.VISIBLE_LINES

        inc_active, ok = project.readBoolEntry("MSACurveMaster", "PourIncludeActiveLayer", True)
        self.include_active_layer_boundaries = inc_active if ok else True

    def _save_boundary_settings(self):
        """Zapisuje wybrane warstwy krawędzi w pliku projektu QGIS."""
        project = QgsProject.instance()
        project.writeEntry("MSACurveMaster", "PourBoundaryLayerIds", list(self.selected_boundary_layer_ids))
        project.writeEntryBool("MSACurveMaster", "PourIncludeActiveLayer", self.include_active_layer_boundaries)
        project.writeEntry("MSACurveMaster", "PourBoundaryScope", self.boundary_scope.value)

    def _set_boundary_scope(self, scope: PourBoundaryScope):
        self.boundary_scope = scope
        self._save_boundary_settings()
        self.cached_boundary_lines = []
        self.cached_boundary_radius = 0.0

    def open_boundary_layers_dialog(self):
        """Otwiera okno wyboru warstw stanowiących krawędzie dla wylewania."""
        try:
            from ..gui.pour_boundary_dialog import PourBoundaryLayersDialog
        except (ImportError, ValueError):
            from gui.pour_boundary_dialog import PourBoundaryLayersDialog

        parent_widget = self.iface.mainWindow() if self.iface else self.canvas().window()
        dlg = PourBoundaryLayersDialog(
            self.selected_boundary_layer_ids,
            self.include_active_layer_boundaries,
            parent_widget
        )
        if dlg.exec_():
            new_ids, inc_active = dlg.get_results()
            self.selected_boundary_layer_ids = new_ids
            self.include_active_layer_boundaries = inc_active
            if self.selected_boundary_layer_ids:
                self.boundary_scope = PourBoundaryScope.CUSTOM_LAYERS
            else:
                self.boundary_scope = PourBoundaryScope.VISIBLE_LINES
            self._save_boundary_settings()

            self.cached_boundary_lines = []
            self.cached_boundary_radius = 0.0

            count = len(self.selected_boundary_layer_ids)
            if self.iface:
                if count > 0:
                    self.iface.messageBar().pushInfo(
                        "MSA: CurveMaster",
                        tr(f"Boundary layers updated: {count} layer(s) selected as curbs.",
                           f"Zaktualizowano warstwy krawędzi: {count} wybranych warstw.")
                    )
                else:
                    self.iface.messageBar().pushInfo(
                        "MSA: CurveMaster",
                        tr("Boundary mode set to: All visible lines.",
                           "Tryb krawędzi: Wszystkie widoczne linie.")
                    )

    def create_dropdown_menu(self, parent=None) -> QMenu:
        """
        Tworzy rozwijane menu dla przycisku wylewania (MenuButtonPopup),
        umożliwiające wybór zakresu warstw krawędzi.
        """
        menu = QMenu(parent or self.canvas())
        menu.setTitle(tr("Smart Pour Boundary Settings", "Ustawienia krawędzi Smart Pour"))

        lbl_hdr = QLabel(tr("  Boundary layers for pouring:", "  Warstwy krawędzi dla wylewania:"))
        lbl_hdr.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
        act_hdr = QWidgetAction(menu)
        act_hdr.setDefaultWidget(lbl_hdr)
        menu.addAction(act_hdr)

        act_open_dlg = menu.addAction(tr("Select Boundary Layers...", "Wskaż warstwy krawędzi..."))
        act_open_dlg.triggered.connect(self.open_boundary_layers_dialog)

        menu.addSeparator()

        group = QActionGroup(menu)
        group.setExclusive(True)

        act_custom = menu.addAction(tr("Only selected layers", "Tylko wybrane warstwy"))
        act_custom.setCheckable(True)
        act_custom.setChecked(self.boundary_scope == PourBoundaryScope.CUSTOM_LAYERS)
        group.addAction(act_custom)
        act_custom.triggered.connect(lambda: self._set_boundary_scope(PourBoundaryScope.CUSTOM_LAYERS))

        act_visible_lines = menu.addAction(tr("All visible line layers", "Wszystkie widoczne linie"))
        act_visible_lines.setCheckable(True)
        act_visible_lines.setChecked(self.boundary_scope == PourBoundaryScope.VISIBLE_LINES)
        group.addAction(act_visible_lines)
        act_visible_lines.triggered.connect(lambda: self._set_boundary_scope(PourBoundaryScope.VISIBLE_LINES))

        menu.addSeparator()

        act_inc_active = menu.addAction(tr("Include boundaries of active layer", "Uwzględniaj granice aktywnej warstwy"))
        act_inc_active.setCheckable(True)
        act_inc_active.setChecked(self.include_active_layer_boundaries)

        def on_toggle_active(checked):
            self.include_active_layer_boundaries = checked
            self._save_boundary_settings()
            self.cached_boundary_lines = []
            self.cached_boundary_radius = 0.0

        act_inc_active.toggled.connect(on_toggle_active)

        def on_about_to_show():
            act_custom.setChecked(self.boundary_scope == PourBoundaryScope.CUSTOM_LAYERS)
            act_visible_lines.setChecked(self.boundary_scope == PourBoundaryScope.VISIBLE_LINES)
            act_inc_active.setChecked(self.include_active_layer_boundaries)
            count = len(self.selected_boundary_layer_ids)
            act_custom.setText(tr(f"Only selected layers ({count})", f"Tylko wybrane warstwy ({count})"))

        menu.aboutToShow.connect(on_about_to_show)
        return menu

    def activate(self):
        super().activate()
        self.canvas().installEventFilter(self)
        self.canvas().setFocus()
        self._refresh_layer_categories()

    def deactivate(self):
        try:
            self.canvas().removeEventFilter(self)
        except Exception as err:
            QgsMessageLog.logMessage(f"Event filter cleanup: {err}", "CurveMaster", Qgis.Info)

        if self._connected_style_layer:
            try:
                self._connected_style_layer.styleChanged.disconnect(self._on_layer_style_changed)
            except Exception as err:
                QgsMessageLog.logMessage(f"Style disconnect cleanup: {err}", "CurveMaster", Qgis.Info)
            self._connected_style_layer = None

        self._clear_all_previews()
        self.overlay.hide()
        self.state = self.STATE_IDLE
        super().deactivate()

    def active_editable_polygon_layer(self) -> Optional[QgsVectorLayer]:
        """Zwraca aktywną warstwę jeśli jest wektorowa, edytowalna i poligonowa."""
        layer = self.canvas().currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            return None
        if not layer.isEditable():
            return None
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            return None
        return layer

    def _on_layer_style_changed(self):
        """Automatycznie odświeża kategorie i barwy badge'a po zmianie stylu warstwy w QGIS."""
        self._refresh_layer_categories()

    def _refresh_layer_categories(self):
        """Pobiera kategorie oraz stylizację z aktywnej warstwy i konfiguruje opcje w HUD i pasku."""
        layer = self.active_editable_polygon_layer()
        if not layer:
            if self.iface:
                self.iface.messageBar().pushInfo(
                    "MSA: CurveMaster",
                    tr("Please enable editing on a polygon layer to pour surfaces.",
                       "Włącz tryb edycji na warstwie poligonowej, aby wylewać nawierzchnie.")
                )
            self.active_categories = [tr("Asphalt", "Asfalt")]
            self.category_styles = {}
            self.settings_widget.set_pour_categories(self.active_categories, self.last_used_category)
            self.overlay.set_category_name(self.active_categories[0], None)
            return

        # Podpięcie pod zmianę stylizacji aktywnej warstwy
        if self._connected_style_layer != layer:
            if self._connected_style_layer:
                try:
                    self._connected_style_layer.styleChanged.disconnect(self._on_layer_style_changed)
                except Exception as err:
                    QgsMessageLog.logMessage(f"Disconnect previous styleChanged: {err}", "CurveMaster", Qgis.Info)
            try:
                layer.styleChanged.connect(self._on_layer_style_changed)
                self._connected_style_layer = layer
            except Exception as err:
                QgsMessageLog.logMessage(f"Connect layer styleChanged: {err}", "CurveMaster", Qgis.Info)

        field_name = find_category_field_name(layer)
        cats = get_layer_unique_categories(layer, field_name)
        if not cats:
            cats = [tr("Asphalt", "Asfalt")]

        self.active_categories = cats
        self.category_styles = get_layer_category_styles(layer, field_name)

        # Domyślny wybór: ostatnio użyty lub pierwszy alfabetycznie
        chosen_cat = self.last_used_category if (self.last_used_category and self.last_used_category in cats) else cats[0]
        self.last_used_category = chosen_cat
        self.current_category_idx = self.active_categories.index(chosen_cat) if chosen_cat in self.active_categories else 0

        chosen_style = find_category_style(self.category_styles, chosen_cat)
        self.settings_widget.set_pour_categories(self.active_categories, chosen_cat, self.category_styles)
        self.overlay.set_category_name(chosen_cat, chosen_style)

    def _get_active_category_display(self) -> str:
        """Zwraca nazwę aktualnie wybranej kategorii."""
        total = len(self.active_categories)
        if self.current_category_idx < total:
            return self.active_categories[self.current_category_idx]
        return tr("[+ New Category...]", "[➕ Nowa kategoria...]")

    def _cycle_category(self, step: int = 1):
        """Przełącza kategorię na kolejną (klawisz Tab)."""
        # Lista kategorii + 1 pozycja na "Nowa kategoria..."
        total_items = len(self.active_categories) + 1
        self.current_category_idx = (self.current_category_idx + step) % total_items

        cat_display = self._get_active_category_display()
        style = find_category_style(self.category_styles, cat_display)
        self.overlay.set_category_name(cat_display, style)
        self.settings_widget.set_current_pour_category(cat_display, style)

    def _on_settings_category_changed(self, cat_text: str):
        """Obsługuje zmianę kategorii bezpośrednio z paska narzędzi."""
        clean_text = cat_text.strip()
        if clean_text in self.active_categories:
            self.current_category_idx = self.active_categories.index(clean_text)
            self.last_used_category = clean_text
        elif "nowa" in clean_text.lower() or "new" in clean_text.lower():
            self.current_category_idx = len(self.active_categories)

        cat_display = self._get_active_category_display()
        style = find_category_style(self.category_styles, cat_display)
        self.overlay.set_category_name(cat_display, style)

    def _collect_boundary_geometries(self, layer: QgsVectorLayer, center_pt: QgsPointXY, radius: float) -> List[QgsGeometry]:
        """
        Zbiera geometrie liniowe i krawędzie poligonów ze wszystkich widocznych warstw
        w zasięgu prostokąta otaczającego bufor.
        """
        search_rect = QgsRectangle(
            center_pt.x() - radius * 1.2,
            center_pt.y() - radius * 1.2,
            center_pt.x() + radius * 1.2,
            center_pt.y() + radius * 1.2
        )

        boundaries: List[QgsGeometry] = []
        layer_crs = layer.crs()
        canvas_crs = self.canvas().mapSettings().destinationCrs()
        project = QgsProject.instance()

        for map_layer in project.mapLayers().values():
            if not isinstance(map_layer, QgsVectorLayer) or not map_layer.isValid():
                continue

            is_active_layer = (map_layer.id() == layer.id())

            # 1. Filtrowanie zakresu warstw krawędzi
            if self.boundary_scope == PourBoundaryScope.CUSTOM_LAYERS:
                if self.selected_boundary_layer_ids:
                    # Warstwa musi być wybrana przez użytkownika lub być aktywną warstwą (jeśli włączona)
                    if map_layer.id() not in self.selected_boundary_layer_ids and not (is_active_layer and self.include_active_layer_boundaries):
                        continue
                else:
                    # Jeśli nie wybrano jeszcze żadnych warstw, filtrujemy domyślnie tylko widoczne linie
                    if not is_active_layer:
                        if map_layer.geometryType() != QgsWkbTypes.LineGeometry:
                            continue
                        tree_layer = project.layerTreeRoot().findLayer(map_layer.id()) if project.layerTreeRoot() else None
                        if tree_layer and not tree_layer.isVisible():
                            continue
            elif self.boundary_scope == PourBoundaryScope.VISIBLE_LINES:
                if not is_active_layer:
                    if map_layer.geometryType() != QgsWkbTypes.LineGeometry:
                        continue
                    tree_layer = project.layerTreeRoot().findLayer(map_layer.id()) if project.layerTreeRoot() else None
                    if tree_layer and not tree_layer.isVisible():
                        continue

            if is_active_layer and not self.include_active_layer_boundaries:
                continue

            # Sprawdzamy tylko warstwy liniowe oraz poligonowe
            geom_type = map_layer.geometryType()
            if geom_type not in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                continue

            # Przygotowanie transformacji CRS do układu aktywnej warstwy
            src_crs = map_layer.crs()
            need_transform = (src_crs != layer_crs and src_crs.isValid() and layer_crs.isValid())
            transform = None
            layer_search_rect = search_rect

            if need_transform:
                try:
                    transform = QgsCoordinateTransform(src_crs, layer_crs, project)
                    layer_to_src = QgsCoordinateTransform(layer_crs, src_crs, project)
                    layer_search_rect = layer_to_src.transformBoundingBox(search_rect)
                except Exception as err:
                    QgsMessageLog.logMessage(f"Błąd transformacji CRS warstwy {map_layer.name()}: {err}", "CurveMaster", Qgis.Info)
                    continue

            req = QgsFeatureRequest().setFilterRect(layer_search_rect)
            for feat in map_layer.getFeatures(req):
                fg = feat.geometry()
                if not fg or fg.isEmpty():
                    continue

                if need_transform and transform:
                    try:
                        fg = QgsGeometry(fg)
                        fg.transform(transform)
                    except Exception as err:
                        QgsMessageLog.logMessage(f"Transformacja geometrii: {err}", "CurveMaster", Qgis.Info)
                        continue

                boundaries.append(fg)

        return boundaries

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.RightButton:
            self._cancel_operation()
            return

        if e.button() == Qt.LeftButton:
            layer = self.active_editable_polygon_layer()
            if not layer:
                if self.iface:
                    self.iface.messageBar().pushWarning(
                        "MSA: CurveMaster",
                        tr("Please select and enable editing on a polygon layer first.",
                           "Zaznacz i włącz tryb edycji na warstwie poligonowej przed wylewaniem.")
                    )
                return

            if self.state == self.STATE_IDLE:
                # Krok 1: Wskazanie punktu startowego P0
                self.start_canvas_pt, self.start_layer_pt = self.snap_point_layer(e, layer)
                self.state = self.STATE_POURING
                self.current_radius = self.last_used_radius

                # Pokaż znacznik P0
                self.start_pt_band.reset(QgsWkbTypes.PointGeometry)
                self.start_pt_band.addPoint(self.start_canvas_pt)

                # Zbierz wstępnie linie obwiedni w promieniu wyszukiwania
                self.cached_boundary_radius = max(self.last_used_radius * 2.0, 100.0)
                self.cached_boundary_lines = self._collect_boundary_geometries(
                    layer, self.start_layer_pt, self.cached_boundary_radius
                )

                # Oblicz pierwszy podgląd i pokaż overlay CAD
                self._update_preview(self.current_radius, self.start_canvas_pt)
                self.overlay.set_last_radius(self.last_used_radius)
                cat_display = self._get_active_category_display()
                style = find_category_style(self.category_styles, cat_display)
                self.overlay.update_values(self.current_radius, cat_display, e.pos(), style)

            elif self.state == self.STATE_POURING:
                # Krok 2: Kliknięcie potwierdza promień i wylewa poligon
                self._commit_pour()

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        if self.state == self.STATE_POURING and self.start_layer_pt:
            layer = self.active_editable_polygon_layer()
            curr_canvas_pt, curr_layer_pt = self.snap_point_layer(e, layer)

            # Promień jako odległość od P0 do kursora
            dx = curr_layer_pt.x() - self.start_layer_pt.x()
            dy = curr_layer_pt.y() - self.start_layer_pt.y()
            radius = math.sqrt(dx * dx + dy * dy)
            self.current_radius = max(0.5, radius)

            # Dynamiczne dociąganie linii jeśli promień przekracza bufor cache
            if radius * 1.2 > self.cached_boundary_radius:
                self.cached_boundary_radius = radius * 2.0
                self.cached_boundary_lines = self._collect_boundary_geometries(
                    layer, self.start_layer_pt, self.cached_boundary_radius
                )

            # Aktualizacja podglądu geometrii i HUD
            self._update_preview(self.current_radius, curr_canvas_pt)
            cat_display = self._get_active_category_display()
            style = find_category_style(self.category_styles, cat_display)
            self.overlay.update_values(self.current_radius, cat_display, e.pos(), style)

    def _update_preview(self, radius: float, curr_canvas_pt: Optional[QgsPointXY] = None):
        """Oblicza i rysuje podgląd poligonu oraz linię promienia."""
        if not self.start_layer_pt:
            return

        poly = compute_pour_polygon(
            self.start_layer_pt,
            radius,
            self.cached_boundary_lines
        )
        self.current_poly_geom = poly

        if poly and not poly.isEmpty():
            layer = self.active_editable_polygon_layer()
            # Konwersja geometrii do CRS płótna dla RubberBand
            canvas_geom = self._to_canvas_geometry(layer, poly)
            self.preview_band.setToGeometry(canvas_geom, layer)
        else:
            self.preview_band.reset(QgsWkbTypes.PolygonGeometry)

        # Rysowanie linii promienia (od P0 do kursora)
        if self.start_canvas_pt and curr_canvas_pt:
            self.guide_band.reset(QgsWkbTypes.LineGeometry)
            self.guide_band.addPoint(self.start_canvas_pt)
            self.guide_band.addPoint(curr_canvas_pt)
        else:
            self.guide_band.reset(QgsWkbTypes.LineGeometry)

    def _to_canvas_geometry(self, layer: Optional[QgsVectorLayer], geom: QgsGeometry) -> QgsGeometry:
        """Konwertuje geometrię z CRS warstwy do CRS płótna mapy."""
        if not layer or not geom:
            return geom
        canvas_crs = self.canvas().mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs == layer_crs or not layer_crs.isValid() or not canvas_crs.isValid():
            return geom
        try:
            trans = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            g = QgsGeometry(geom)
            g.transform(trans)
            return g
        except Exception as err:
            QgsMessageLog.logMessage(f"Błąd transformacji geometrii do canvas: {err}", "CurveMaster", Qgis.Info)
            return geom

    def _on_overlay_radius_submitted(self, radius: float):
        """Obsługa zatwierdzenia wpisanej wartości promienia z klawiatury."""
        self.current_radius = radius
        self._commit_pour()

    def _commit_pour(self):
        """Zatwierdza wylanie nawierzchni, tworzy poligon i wykonuje Auto-Merge."""
        layer = self.active_editable_polygon_layer()
        if not layer or not self.start_layer_pt:
            self._cancel_operation()
            return

        # Przeliczenie ostatecznego poligonu
        poly = compute_pour_polygon(
            self.start_layer_pt,
            self.current_radius,
            self.cached_boundary_lines
        )

        if not poly or poly.isEmpty():
            if self.iface:
                self.iface.messageBar().pushWarning(
                    "MSA: CurveMaster",
                    tr("Could not construct polygon inside boundary at this radius.",
                       "Nie udało się wyznaczyć poligonu obwiedni przy tym zasięgu.")
                )
            self._cancel_operation()
            return

        # Obsługa kategorii: jeśli wybrano [Nowa kategoria...], pytamy użytkownika o nazwę
        category_to_apply = ""
        total_cats = len(self.active_categories)
        if self.current_category_idx < total_cats:
            category_to_apply = self.active_categories[self.current_category_idx]
        else:
            # Okno dialogowe nowej kategorii
            parent_widget = self.iface.mainWindow() if self.iface else self.canvas().window()
            new_cat_name, ok = QInputDialog.getText(
                parent_widget,
                tr("New Surface Category", "Nowa kategoria nawierzchni"),
                tr("Enter category name for poured surface (e.g. grass, bike path):",
                   "Wpisz nazwę nowej kategorii nawierzchni (np. trawa, ddr):"),
                QLineEdit.Normal,
                ""
            )
            if not ok or not new_cat_name.strip():
                # Użytkownik anulował wprowadzanie
                self._cancel_operation()
                return

            category_to_apply = new_cat_name.strip()
            # Dodanie do listy i zapamiętanie
            if category_to_apply not in self.active_categories:
                self.active_categories.append(category_to_apply)
                self.active_categories.sort(key=lambda x: x.lower())
                self.settings_widget.set_pour_categories(self.active_categories, category_to_apply)

        # Zapamiętujemy jako ostatnio użytą
        self.last_used_category = category_to_apply
        self.last_used_radius = self.current_radius
        PavementPourTool.last_used_category = category_to_apply
        PavementPourTool.last_used_radius = self.current_radius

        # Zapewnienie istnienia kolumny kategorii w warstwie
        field_name = find_category_field_name(layer)
        if not field_name:
            # Automatycznie dodajemy pole 'kategoria' do warstwy
            try:
                layer.dataProvider().addAttributes([QgsField("kategoria", QVariant.String)])
                layer.updateFields()
                field_name = "kategoria"
            except Exception as err:
                QgsMessageLog.logMessage(f"Błąd dodawania pola kategoria: {err}", "CurveMaster", Qgis.Warning)

        # Wykonanie Auto-Merge / wstawienia do warstwy
        success = merge_polygon_with_category(
            layer,
            poly,
            field_name,
            category_to_apply,
            command_name=tr("MSA: Pour Pavement", "MSA: Zalej nawierzchnię")
        )

        if success and self.iface:
            self.iface.messageBar().pushSuccess(
                "MSA: CurveMaster",
                tr(f"Successfully poured surface: {category_to_apply}",
                   f"Pomyślnie wylano nawierzchnię: {category_to_apply}")
            )

        self._cancel_operation()

    def _cancel_operation(self):
        """Anuluje operację i czyści podglądy."""
        self._clear_all_previews()
        self.overlay.hide()
        self.start_canvas_pt = None
        self.start_layer_pt = None
        self.current_poly_geom = None
        self.cached_boundary_lines = []
        self.cached_boundary_radius = 0.0
        self.state = self.STATE_IDLE

    def _clear_all_previews(self):
        if self.preview_band:
            self.preview_band.reset(QgsWkbTypes.PolygonGeometry)
        if self.guide_band:
            self.guide_band.reset(QgsWkbTypes.LineGeometry)
        if self.start_pt_band:
            self.start_pt_band.reset(QgsWkbTypes.PointGeometry)

    def eventFilter(self, obj, event):
        """Przechwytuje klawisze Tab, Shift+Tab oraz Enter na płótnie mapy."""
        if obj == self.canvas() and event.type() == QEvent.KeyPress:
            key = event.key()
            if self.state == self.STATE_POURING:
                if key == Qt.Key_Tab:
                    if event.modifiers() & Qt.ShiftModifier:
                        self._cycle_category(-1)
                    else:
                        self._cycle_category(1)
                    return True
                elif key == Qt.Key_Backtab:
                    self._cycle_category(-1)
                    return True
                elif key in (Qt.Key_Return, Qt.Key_Enter):
                    self._commit_pour()
                    return True
                elif key == Qt.Key_Escape:
                    self._cancel_operation()
                    return True

        return super().eventFilter(obj, event)
