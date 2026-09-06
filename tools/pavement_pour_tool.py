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
from typing import Optional, List, Set, Dict, Tuple
from qgis.PyQt.QtCore import Qt, QPoint, QEvent, QVariant
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import (
    QInputDialog,
    QLineEdit,
    QMenu,
    QActionGroup,
    QWidgetAction,
    QLabel,
    QApplication
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
    find_category_style,
    find_polygon_feature_at_point,
    erase_polygon_with_radius
)
try:
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.i18n import tr


class PourMode(Enum):
    """Tryb działania narzędzia: wylewanie nawierzchni lub wycinanie (gumka CAD)."""
    POUR = "pour"    # Zwykłe kliknięcie: wylewanie z Auto-Merge
    ERASE = "erase"  # Shift + Kliknięcie: wycinanie/usuwanie fragmentu z poligonu


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
        self.pour_mode: PourMode = PourMode.POUR
        self.target_erase_feature_id: Optional[int] = None
        self.target_erase_geom: Optional[QgsGeometry] = None
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
        self._last_canvas_pt: Optional[QgsPointXY] = None
        self._last_mouse_pos: QPoint = QPoint(0, 0)

        # Zakres warstw krawędzi (bariery)
        self.selected_boundary_layer_ids: Set[str] = set()
        self.include_active_layer_boundaries: bool = True
        self.boundary_scope: PourBoundaryScope = PourBoundaryScope.CUSTOM_LAYERS
        self._load_boundary_settings()

        # Synchronizacja ze zmianą w pasku ustawień
        self.selected_category_field: Optional[str] = None
        self.settings_widget.pourFieldChanged.connect(self._on_settings_field_changed)
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

        menu.addSeparator()

        lbl_field_hdr = QLabel(tr("  Differentiating field (Category):", "  Pole różnicujące (kategoria):"))
        lbl_field_hdr.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
        act_fhdr = QWidgetAction(menu)
        act_fhdr.setDefaultWidget(lbl_field_hdr)
        menu.addAction(act_fhdr)

        field_menu = menu.addMenu(tr("Select category field...", "Wybierz pole kategorii..."))

        def on_about_to_show():
            act_custom.setChecked(self.boundary_scope == PourBoundaryScope.CUSTOM_LAYERS)
            act_visible_lines.setChecked(self.boundary_scope == PourBoundaryScope.VISIBLE_LINES)
            act_inc_active.setChecked(self.include_active_layer_boundaries)
            count = len(self.selected_boundary_layer_ids)
            act_custom.setText(tr(f"Only selected layers ({count})", f"Tylko wybrane warstwy ({count})"))

            # Aktualizacja menu wyboru pola kategorii
            field_menu.clear()
            layer = self.active_editable_polygon_layer()
            if layer:
                grp_fields = QActionGroup(field_menu)
                grp_fields.setExclusive(True)

                act_none = field_menu.addAction(tr("[None] No category field", "[Brak] Bez pola kategorii"))
                act_none.setCheckable(True)
                act_none.setChecked(self.selected_category_field is None)
                grp_fields.addAction(act_none)
                act_none.triggered.connect(lambda: self._set_field_from_menu(None))

                for f in layer.fields():
                    fname = f.name()
                    act_f = field_menu.addAction(fname)
                    act_f.setCheckable(True)
                    act_f.setChecked(self.selected_category_field == fname)
                    grp_fields.addAction(act_f)
                    act_f.triggered.connect(lambda checked, fn=fname: self._set_field_from_menu(fn))
            else:
                act_no = field_menu.addAction(tr("No editable polygon layer", "Brak edytowalnej warstwy"))
                act_no.setEnabled(False)

        menu.aboutToShow.connect(on_about_to_show)
        return menu

    def _set_field_from_menu(self, field_name: Optional[str]):
        """Obsługuje wybór pola kategorii z menu rozwijanego."""
        self.selected_category_field = field_name
        self.settings_widget.combo_pour_field.blockSignals(True)
        idx = self.settings_widget.combo_pour_field.findData(field_name or "")
        if idx >= 0:
            self.settings_widget.combo_pour_field.setCurrentIndex(idx)
        self.settings_widget.combo_pour_field.blockSignals(False)
        layer = self.active_editable_polygon_layer()
        if layer:
            self._update_category_state(layer)

    def _set_status_tip(self, text: str):
        if self.iface:
            self.iface.mainWindow().statusBar().showMessage(text, 3500)

    def activate(self):
        super().activate()
        self.canvas().installEventFilter(self)
        self.canvas().setFocus()
        self._refresh_layer_categories()
        self._set_status_tip(tr(
            "MSA Smart Pour: Kliknij, aby zalać | Shift + Klik = Gumka CAD (Wytnij fragment)",
            "MSA Smart Pour: Kliknij, aby zalać | Shift + Klik = Gumka CAD (Wytnij fragment)"
        ))

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
            self.active_categories = []
            self.category_styles = {}
            self.selected_category_field = None
            self.settings_widget.set_pour_fields([], None)
            self.settings_widget.set_pour_categories([], None, None, has_field=False)
            self.overlay.set_category_name(tr("[No Category]", "[Brak kategorii]"), None, has_field=False)
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

        layer_field_names = [f.name() for f in layer.fields()]

        # Jeśli użytkownik jeszcze nie wybrał pola lub pole nie istnieje w bieżącej warstwie:
        # Sprawdzamy czy warstwa posiada atrybut w stylizacji skategoryzowanej (bez zgadywania!)
        if not self.selected_category_field or self.selected_category_field not in layer_field_names:
            self.selected_category_field = find_category_field_name(layer)

        # Ustawiamy dostępne pola na pasku narzędzi
        self.settings_widget.set_pour_fields(layer_field_names, self.selected_category_field)
        self._update_category_state(layer)

    def _on_settings_field_changed(self, field_name: str):
        """Obsługuje wybór atrybutu różnicującego z paska narzędzi."""
        clean = field_name.strip() if field_name else None
        self.selected_category_field = clean if clean else None
        layer = self.active_editable_polygon_layer()
        if layer:
            self._update_category_state(layer)

    def _update_category_state(self, layer: QgsVectorLayer):
        """Aktualizuje listę kategorii i stylizację dla wybranego pola."""
        field_name = self.selected_category_field
        has_field = bool(field_name and layer.fields().indexOf(field_name) >= 0)

        if not has_field:
            self.active_categories = []
            self.category_styles = {}
            self.current_category_idx = 0
            self.settings_widget.set_pour_categories([], None, None, has_field=False)
            self.overlay.set_category_name(tr("[No Category]", "[Brak kategorii]"), None, has_field=False)
            return

        cats = get_layer_unique_categories(layer, field_name)
        self.active_categories = cats
        self.category_styles = get_layer_category_styles(layer, field_name)

        if not cats:
            # Pole jest wybrane, ale nie ma jeszcze żadnych zdefiniowanych rodzajów
            self.current_category_idx = 0
            cat_display = tr("[+ New Category...]", "[➕ Nowa kategoria...]")
            self.settings_widget.set_pour_categories([], cat_display, self.category_styles, has_field=True)
            self.overlay.set_category_name(cat_display, None, has_field=True)
        else:
            chosen_cat = self.last_used_category if (self.last_used_category and self.last_used_category in cats) else cats[0]
            self.last_used_category = chosen_cat
            self.current_category_idx = self.active_categories.index(chosen_cat)
            chosen_style = find_category_style(self.category_styles, chosen_cat)
            self.settings_widget.set_pour_categories(self.active_categories, chosen_cat, self.category_styles, has_field=True)
            self.overlay.set_category_name(chosen_cat, chosen_style, has_field=True)

    def _get_active_category_display(self) -> str:
        """Zwraca nazwę aktualnie wybranej kategorii."""
        if not self.selected_category_field:
            return tr("[No Category]", "[Brak kategorii]")
        total = len(self.active_categories)
        if total == 0:
            return tr("[+ New Category...]", "[➕ Nowa kategoria...]")
        if self.current_category_idx < total:
            return self.active_categories[self.current_category_idx]
        return tr("[+ New Category...]", "[➕ Nowa kategoria...]")

    def _cycle_category(self, step: int = 1):
        """Przełącza kategorię na kolejną (klawisz Tab)."""
        if not self.selected_category_field:
            return

        total_cats = len(self.active_categories)
        if total_cats == 0:
            return

        # Lista kategorii + 1 pozycja na "Nowa kategoria..."
        total_items = total_cats + 1
        self.current_category_idx = (self.current_category_idx + step) % total_items

        cat_display = self._get_active_category_display()
        style = find_category_style(self.category_styles, cat_display)
        self.overlay.set_category_name(cat_display, style, has_field=True)
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
        has_field = bool(self.selected_category_field)
        self.overlay.set_category_name(cat_display, style, has_field=has_field)

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

    def raw_point_layer(self, e: QgsMapMouseEvent, layer: Optional[QgsVectorLayer] = None) -> Tuple[QgsPointXY, QgsPointXY]:
        """
        Zwraca krotkę (canvas_point, layer_point) bez używania mechanizmu przyciągania (snapping).
        Dzięki temu punkt początkowy P0 i promień wylewania trafiają dokładnie w miejsce kliknięcia.
        """
        canvas_pt = QgsPointXY(e.mapPoint())
        layer_pt = self.to_layer_point(layer, canvas_pt) if layer else canvas_pt
        return canvas_pt, layer_pt

    def _switch_pour_mode(
        self,
        new_mode: PourMode,
        curr_canvas_pt: Optional[QgsPointXY] = None,
        mouse_pos: Optional[QPoint] = None
    ):
        """
        Dynamicznie przełącza tryb pomiędzy wylewaniem (POUR) a wycinaniem (ERASE).
        Aktualizuje barwy gumek podglądu, geometrię wycinka/wylania oraz nakładkę HUD CAD.
        """
        if self.state != self.STATE_POURING:
            return

        if new_mode == PourMode.ERASE and not self.target_erase_geom:
            self._set_status_tip(tr(
                "MSA Smart Pour: Punkt początkowy nie leży na żadnym obiekcie nawierzchni - brak poligonu do wycięcia.",
                "MSA Smart Pour: Start point is not on any pavement feature - no polygon to erase."
            ))
            return

        if self.pour_mode == new_mode:
            return

        self.pour_mode = new_mode
        canvas_pt = curr_canvas_pt or self._last_canvas_pt or self.start_canvas_pt
        pos = mouse_pos or self._last_mouse_pos

        if self.pour_mode == PourMode.ERASE:
            # Czerwone gumki podglądu dla trybu wycinania
            self.preview_band.setColor(QColor(220, 53, 69, 110))
            self.preview_band.setStrokeColor(QColor(220, 53, 69, 230))
            self.start_pt_band.setColor(QColor(220, 53, 69, 230))
            self._update_preview(self.current_radius, canvas_pt)
            self.overlay.update_values(
                self.current_radius, "", pos, None, has_field=False, is_erase=True
            )
            self._set_status_tip(tr(
                "MSA Smart Pour: [GUMKA CAD] Wycinanie fragmentu nawierzchni (trzymaj Shift). Puść Shift, aby wylewać.",
                "MSA Smart Pour: [CAD ERASER] Erasing pavement section (hold Shift). Release Shift to pour."
            ))
        else:
            # Błękitne gumki podglądu dla trybu wylewania
            self.preview_band.setColor(QColor(13, 110, 253, 90))
            self.preview_band.setStrokeColor(QColor(13, 110, 253, 220))
            self.start_pt_band.setColor(QColor(13, 110, 253, 230))
            self._update_preview(self.current_radius, canvas_pt)
            cat_display = self._get_active_category_display()
            style = find_category_style(self.category_styles, cat_display)
            has_field = bool(self.selected_category_field)
            self.overlay.update_values(
                self.current_radius, cat_display, pos, style, has_field=has_field, is_erase=False
            )
            self._set_status_tip(tr(
                "MSA Smart Pour: Wylewanie nawierzchni. Naciśnij i przytrzymaj Shift, aby wyciąć fragment gumką CAD.",
                "MSA Smart Pour: Pouring pavement. Press and hold Shift to erase section with CAD eraser."
            ))

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
                # Krok 1: Wskazanie punktu startowego P0 (bez snappingu!)
                self.start_canvas_pt, self.start_layer_pt = self.raw_point_layer(e, layer)
                self._last_canvas_pt = self.start_canvas_pt
                self._last_mouse_pos = e.pos()

                is_shift = bool(e.modifiers() & Qt.ShiftModifier) or bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)

                # Wyszukaj obiekt nawierzchni pod P0 dla potencjalnego trybu wycinania
                tol = max(0.1, self.canvas().mapUnitsPerPixel() * 5) if self.canvas() else 0.1
                target_feat = find_polygon_feature_at_point(layer, self.start_layer_pt, tolerance=tol)
                if target_feat:
                    self.target_erase_feature_id = target_feat.id()
                    self.target_erase_geom = QgsGeometry(target_feat.geometry())
                else:
                    self.target_erase_feature_id = None
                    self.target_erase_geom = None

                if is_shift and not target_feat:
                    if self.iface:
                        self.iface.messageBar().pushInfo(
                            "MSA: CurveMaster",
                            tr("No surface polygon found under cursor to erase.",
                               "Nie znaleziono obiektu nawierzchni pod kursorem do wycięcia.")
                        )
                    return

                # Zbierz wstępnie linie obwiedni w promieniu wyszukiwania dla trybu wylewania
                self.cached_boundary_radius = max(self.last_used_radius * 2.0, 100.0)
                self.cached_boundary_lines = self._collect_boundary_geometries(
                    layer, self.start_layer_pt, self.cached_boundary_radius
                )

                self.state = self.STATE_POURING
                self.current_radius = self.last_used_radius

                # Pokaż znacznik P0
                self.start_pt_band.reset(QgsWkbTypes.PointGeometry)
                self.start_pt_band.addPoint(self.start_canvas_pt)

                # Wstępne ustawienie trybu w zależności od Shift
                self.pour_mode = PourMode.ERASE if is_shift else PourMode.POUR

                if self.pour_mode == PourMode.ERASE:
                    # Czerwone gumki podglądu dla trybu wycinania
                    self.preview_band.setColor(QColor(220, 53, 69, 110))
                    self.preview_band.setStrokeColor(QColor(220, 53, 69, 230))
                    self.start_pt_band.setColor(QColor(220, 53, 69, 230))
                    self._update_preview(self.current_radius, self.start_canvas_pt)
                    self.overlay.set_last_radius(self.last_used_radius)
                    self.overlay.update_values(
                        self.current_radius, "", e.pos(), None, has_field=False, is_erase=True
                    )
                    self._set_status_tip(tr(
                        "MSA Smart Pour: [GUMKA CAD] Wycinanie fragmentu nawierzchni (trzymaj Shift). Puść Shift, aby wylewać.",
                        "MSA Smart Pour: [CAD ERASER] Erasing pavement section (hold Shift). Release Shift to pour."
                    ))
                else:
                    # Błękitne gumki podglądu dla trybu wylewania
                    self.preview_band.setColor(QColor(13, 110, 253, 90))
                    self.preview_band.setStrokeColor(QColor(13, 110, 253, 220))
                    self.start_pt_band.setColor(QColor(13, 110, 253, 230))
                    self._update_preview(self.current_radius, self.start_canvas_pt)
                    self.overlay.set_last_radius(self.last_used_radius)
                    cat_display = self._get_active_category_display()
                    style = find_category_style(self.category_styles, cat_display)
                    has_field = bool(self.selected_category_field)
                    self.overlay.update_values(
                        self.current_radius, cat_display, e.pos(), style, has_field=has_field, is_erase=False
                    )
                    self._set_status_tip(tr(
                        "MSA Smart Pour: Wylewanie nawierzchni. Naciśnij i przytrzymaj Shift, aby wyciąć fragment gumką CAD.",
                        "MSA Smart Pour: Pouring pavement. Press and hold Shift to erase section with CAD eraser."
                    ))

            elif self.state == self.STATE_POURING:
                # Krok 2: Kliknięcie potwierdza promień i zatwierdza operację
                is_shift = bool(e.modifiers() & Qt.ShiftModifier) or bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
                if is_shift and self.target_erase_geom:
                    self.pour_mode = PourMode.ERASE
                elif not is_shift and not self.overlay.edit_radius.hasFocus():
                    self.pour_mode = PourMode.POUR

                if self.pour_mode == PourMode.ERASE:
                    self._commit_erase()
                else:
                    self._commit_pour()

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        if self.state == self.STATE_POURING and self.start_layer_pt:
            layer = self.active_editable_polygon_layer()
            curr_canvas_pt, curr_layer_pt = self.raw_point_layer(e, layer)
            self._last_canvas_pt = curr_canvas_pt
            self._last_mouse_pos = e.pos()

            # Promień jako odległość od P0 do kursora
            dx = curr_layer_pt.x() - self.start_layer_pt.x()
            dy = curr_layer_pt.y() - self.start_layer_pt.y()
            radius = math.sqrt(dx * dx + dy * dy)
            self.current_radius = max(0.5, radius)

            # Dynamiczne sprawdzanie stanu Shift podczas przeciągania
            if not self.overlay.edit_radius.hasFocus():
                is_shift = bool(e.modifiers() & Qt.ShiftModifier) or bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
                desired_mode = PourMode.ERASE if is_shift else PourMode.POUR
                if desired_mode != self.pour_mode and (desired_mode == PourMode.POUR or self.target_erase_geom):
                    self._switch_pour_mode(desired_mode, curr_canvas_pt, e.pos())
                    return

            if self.pour_mode == PourMode.ERASE:
                self._update_preview(self.current_radius, curr_canvas_pt)
                self.overlay.update_values(
                    self.current_radius, "", e.pos(), None, has_field=False, is_erase=True
                )
            else:
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
                has_field = bool(self.selected_category_field)
                self.overlay.update_values(
                    self.current_radius, cat_display, e.pos(), style, has_field=has_field, is_erase=False
                )
        elif self.state == self.STATE_IDLE:
            is_shift = bool(e.modifiers() & Qt.ShiftModifier) or bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
            if is_shift:
                self._set_status_tip(tr(
                    "MSA Smart Pour: [GUMKA CAD] Kliknij i przytrzymaj Shift, aby wyciąć fragment poligonu.",
                    "MSA Smart Pour: [CAD ERASER] Click and hold Shift to erase polygon section."
                ))

    def _update_preview(self, radius: float, curr_canvas_pt: Optional[QgsPointXY] = None):
        """Oblicza i rysuje podgląd poligonu oraz linię promienia."""
        if not self.start_layer_pt:
            return

        layer = self.active_editable_polygon_layer()

        if self.pour_mode == PourMode.ERASE:
            # W trybie wycinania podgląd to część wspólna obiektu i kołowego dysku wokół P0
            if self.target_erase_geom and not self.target_erase_geom.isEmpty():
                pt_geom = QgsGeometry.fromPointXY(self.start_layer_pt)
                disk = pt_geom.buffer(radius, 36)
                cut_preview = self.target_erase_geom.intersection(disk)
                self.current_poly_geom = cut_preview
                if cut_preview and not cut_preview.isEmpty():
                    canvas_geom = self._to_canvas_geometry(layer, cut_preview)
                    self.preview_band.setToGeometry(canvas_geom, None)
                else:
                    self.preview_band.reset(QgsWkbTypes.PolygonGeometry)
            else:
                self.preview_band.reset(QgsWkbTypes.PolygonGeometry)
        else:
            poly = compute_pour_polygon(
                self.start_layer_pt,
                radius,
                self.cached_boundary_lines
            )
            self.current_poly_geom = poly

            if poly and not poly.isEmpty():
                canvas_geom = self._to_canvas_geometry(layer, poly)
                self.preview_band.setToGeometry(canvas_geom, None)
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
        if self.pour_mode == PourMode.ERASE:
            self._commit_erase()
        else:
            self._commit_pour()

    def _commit_erase(self):
        """Zatwierdza wycięcie fragmentu nawierzchni i aktualizuje geometrię lub usuwa obiekt."""
        layer = self.active_editable_polygon_layer()
        if not layer or not self.start_layer_pt or self.target_erase_feature_id is None:
            self._cancel_operation()
            return

        feature_id = self.target_erase_feature_id
        radius = self.current_radius

        success = erase_polygon_with_radius(
            layer,
            feature_id,
            self.start_layer_pt,
            radius,
            command_name=tr("MSA: Wytnij fragment nawierzchni", "MSA: Wytnij fragment nawierzchni")
        )

        if success:
            self.last_used_radius = radius
            PavementPourTool.last_used_radius = radius
            if self.iface:
                self.iface.messageBar().pushSuccess(
                    "MSA: CurveMaster",
                    tr(f"Successfully erased pavement section (R = {radius:.2f} m).",
                       f"Pomyślnie wycięto fragment nawierzchni (R = {radius:.2f} m).")
                )
        else:
            if self.iface:
                self.iface.messageBar().pushWarning(
                    "MSA: CurveMaster",
                    tr("Could not erase pavement section at this radius.",
                       "Nie udało się wyciąć fragmentu nawierzchni przy tym promieniu.")
                )

        self._cancel_operation()

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

        # Obsługa kategorii
        category_to_apply = ""
        field_name = self.selected_category_field

        if field_name:
            total_cats = len(self.active_categories)
            if total_cats > 0 and self.current_category_idx < total_cats:
                category_to_apply = self.active_categories[self.current_category_idx]
            else:
                # Okno dialogowe nowej kategorii
                parent_widget = self.iface.mainWindow() if self.iface else self.canvas().window()
                new_cat_name, ok = QInputDialog.getText(
                    parent_widget,
                    tr("New Surface Category", "Nowa kategoria nawierzchni"),
                    tr("Enter category name for poured surface:",
                       "Wpisz nazwę nowej kategorii nawierzchni:"),
                    QLineEdit.Normal,
                    ""
                )
                if not ok or not new_cat_name.strip():
                    # Użytkownik anulował wprowadzanie
                    self._cancel_operation()
                    return

                category_to_apply = new_cat_name.strip()
                if category_to_apply not in self.active_categories:
                    self.active_categories.append(category_to_apply)
                    self.active_categories.sort(key=lambda x: x.lower())
                    self.current_category_idx = self.active_categories.index(category_to_apply)
                    self.settings_widget.set_pour_categories(
                        self.active_categories, category_to_apply, self.category_styles, has_field=True
                    )

        # Zapamiętujemy jako ostatnio użytą
        if category_to_apply:
            self.last_used_category = category_to_apply
            PavementPourTool.last_used_category = category_to_apply
        self.last_used_radius = self.current_radius
        PavementPourTool.last_used_radius = self.current_radius

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
        self.overlay.set_erase_mode(False)
        self.start_canvas_pt = None
        self.start_layer_pt = None
        self.current_poly_geom = None
        self.cached_boundary_lines = []
        self.cached_boundary_radius = 0.0
        self.pour_mode = PourMode.POUR
        self.target_erase_feature_id = None
        self.target_erase_geom = None
        # Przywrócenie domyślnych kolorów podglądu wylewania
        self.preview_band.setColor(QColor(13, 110, 253, 90))
        self.preview_band.setStrokeColor(QColor(13, 110, 253, 220))
        self.start_pt_band.setColor(QColor(13, 110, 253, 230))
        self.state = self.STATE_IDLE

    def _clear_all_previews(self):
        if self.preview_band:
            self.preview_band.reset(QgsWkbTypes.PolygonGeometry)
        if self.guide_band:
            self.guide_band.reset(QgsWkbTypes.LineGeometry)
        if self.start_pt_band:
            self.start_pt_band.reset(QgsWkbTypes.PointGeometry)

    def keyPressEvent(self, e):
        if self.state == self.STATE_POURING and e.key() == Qt.Key_Shift:
            self._switch_pour_mode(PourMode.ERASE)
            return
        elif e.key() == Qt.Key_Escape:
            self._cancel_operation()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if self.state == self.STATE_POURING and e.key() == Qt.Key_Shift:
            if not self.overlay.edit_radius.hasFocus():
                self._switch_pour_mode(PourMode.POUR)
            return
        super().keyReleaseEvent(e)

    def eventFilter(self, obj, event):
        """Przechwytuje klawisze Tab, Shift, Enter oraz Escape na płótnie mapy."""
        if obj == self.canvas():
            if event.type() == QEvent.KeyPress:
                key = event.key()
                if self.state == self.STATE_POURING:
                    if key == Qt.Key_Shift:
                        self._switch_pour_mode(PourMode.ERASE)
                        return True
                    elif key in (Qt.Key_Tab, Qt.Key_Backtab):
                        if self.pour_mode == PourMode.ERASE:
                            return True
                        if key == Qt.Key_Backtab:
                            self._cycle_category(-1)
                        else:
                            self._cycle_category(1)
                        return True
                    elif key in (Qt.Key_Return, Qt.Key_Enter):
                        if self.pour_mode == PourMode.ERASE:
                            self._commit_erase()
                        else:
                            self._commit_pour()
                        return True
                    elif key == Qt.Key_Escape:
                        self._cancel_operation()
                        return True
            elif event.type() == QEvent.KeyRelease:
                key = event.key()
                if self.state == self.STATE_POURING and key == Qt.Key_Shift:
                    if not self.overlay.edit_radius.hasFocus():
                        self._switch_pour_mode(PourMode.POUR)
                        return True

        return super().eventFilter(obj, event)
