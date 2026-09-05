#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
***************************************************************************
*   MSA: CurveMaster - Okno dialogowe wyboru warstw krawędzi Smart Pour   *
*   Autor: Mikołaj Sazonov                                                *
***************************************************************************
"""

from typing import Set, List, Optional
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QCheckBox,
    QDialogButtonBox,
    QAbstractItemView
)
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes
)
try:
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.i18n import tr


class PourBoundaryLayersDialog(QDialog):
    """
    Okno dialogowe umożliwiające wskazanie warstw projektu,
    które mają stanowić krawędzie (bariery) dla narzędzia Smart Pour.
    """

    def __init__(self, selected_layer_ids: Set[str], include_active_layer: bool = True, parent=None):
        super().__init__(parent)
        self.selected_layer_ids: Set[str] = set(selected_layer_ids)
        self.include_active_layer: bool = include_active_layer
        self.layers_cache: List[QgsVectorLayer] = []
        self._init_ui()
        self._populate_layers()

    def _init_ui(self):
        self.setWindowTitle(tr("Select Boundary Layers — Smart Pour", "Wybór warstw krawędzi — Smart Pour"))
        self.resize(560, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Informacja nagłówkowa
        lbl_info = QLabel(tr(
            "Select which vector layers should act as boundaries/curbs for pavement pouring.\n"
            "Unselected layers (e.g. parcels, utility networks, background polygons) will be ignored.",
            "Wskaż warstwy wektorowe, które mają stanowić granice/krawężniki dla wylewania nawierzchni.\n"
            "Odznaczone warstwy (np. działki, sieci uzbrojenia, budynki) będą całkowicie ignorowane."
        ))
        lbl_info.setStyleSheet("color: #495057; font-size: 11px;")
        layout.addWidget(lbl_info)

        # Wyszukiwarka warstw
        search_layout = QHBoxLayout()
        search_layout.setSpacing(6)
        lbl_search = QLabel(tr("Filter:", "Szukaj:"))
        lbl_search.setStyleSheet("font-weight: bold;")
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText(tr("Type layer name...", "Wpisz nazwę warstwy..."))
        self.edit_filter.textChanged.connect(self._apply_filter)
        search_layout.addWidget(lbl_search)
        search_layout.addWidget(self.edit_filter)
        layout.addLayout(search_layout)

        # Tabela warstw
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([
            tr("Layer Name", "Nazwa warstwy"),
            tr("Type", "Typ"),
            tr("Features", "Obiektów")
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # Szybkie przyciski zaznaczania
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_select_visible_lines = QPushButton(tr("Select Visible Lines", "Zaznacz widoczne linie"))
        self.btn_select_visible_lines.clicked.connect(self._select_visible_lines)
        btn_layout.addWidget(self.btn_select_visible_lines)

        self.btn_select_all_lines = QPushButton(tr("Select All Lines", "Zaznacz wszystkie linie"))
        self.btn_select_all_lines.clicked.connect(self._select_all_lines)
        btn_layout.addWidget(self.btn_select_all_lines)

        self.btn_clear_all = QPushButton(tr("Clear All", "Odznacz wszystkie"))
        self.btn_clear_all.clicked.connect(self._clear_all)
        btn_layout.addWidget(self.btn_clear_all)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Opcja uwzględniania edytowanej warstwy
        self.chk_include_active = QCheckBox(tr(
            "Include boundaries of already poured pavements in active layer",
            "Uwzględniaj granice istniejących nawierzchni w edytowanej warstwie"
        ))
        self.chk_include_active.setChecked(self.include_active_layer)
        self.chk_include_active.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(self.chk_include_active)

        # Przyciski OK / Anuluj
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _populate_layers(self):
        """Wypełnia tabelę warstwami wektorowymi projektu (linie i poligony)."""
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        project = QgsProject.instance()
        all_layers = list(project.mapLayers().values())

        # Filtrujemy tylko warstwy wektorowe liniowe i poligonowe
        valid_layers: List[QgsVectorLayer] = []
        for l in all_layers:
            if isinstance(l, QgsVectorLayer) and l.isValid():
                if l.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                    valid_layers.append(l)

        # Sortowanie: najpierw linie, potem poligony; wewnątrz alfabetycznie
        valid_layers.sort(key=lambda x: (0 if x.geometryType() == QgsWkbTypes.LineGeometry else 1, x.name().lower()))
        self.layers_cache = valid_layers

        for row_idx, lyr in enumerate(valid_layers):
            self.table.insertRow(row_idx)

            # Kolumna 0: Nazwa z Checkboxem
            item_name = QTableWidgetItem(lyr.name())
            item_name.setData(Qt.UserRole, lyr.id())
            is_checked = lyr.id() in self.selected_layer_ids
            item_name.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)

            # Kolumna 1: Typ geometrii
            is_line = lyr.geometryType() == QgsWkbTypes.LineGeometry
            type_str = tr("Line", "Linia") if is_line else tr("Polygon", "Poligon")
            item_type = QTableWidgetItem(type_str)
            item_type.setFlags(item_type.flags() & ~Qt.ItemIsEditable)

            # Kolumna 2: Liczba obiektów
            count_str = str(lyr.featureCount())
            item_count = QTableWidgetItem(count_str)
            item_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_count.setFlags(item_count.flags() & ~Qt.ItemIsEditable)

            self.table.setItem(row_idx, 0, item_name)
            self.table.setItem(row_idx, 1, item_type)
            self.table.setItem(row_idx, 2, item_count)

        self.table.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            lyr_id = item.data(Qt.UserRole)
            if item.checkState() == Qt.Checked:
                self.selected_layer_ids.add(lyr_id)
            else:
                self.selected_layer_ids.discard(lyr_id)

    def _apply_filter(self, text: str):
        query = text.strip().lower()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            matches = query in name_item.text().lower() if name_item else True
            self.table.setRowHidden(row, not matches)

    def _select_visible_lines(self):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            lyr_id = name_item.data(Qt.UserRole)
            lyr = project.mapLayer(lyr_id)
            if lyr and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                tree_layer = root.findLayer(lyr_id) if root else None
                is_visible = tree_layer.isVisible() if tree_layer else True
                if is_visible:
                    name_item.setCheckState(Qt.Checked)
                    self.selected_layer_ids.add(lyr_id)
                else:
                    name_item.setCheckState(Qt.Unchecked)
                    self.selected_layer_ids.discard(lyr_id)
            else:
                name_item.setCheckState(Qt.Unchecked)
                self.selected_layer_ids.discard(lyr_id)
        self.table.blockSignals(False)

    def _select_all_lines(self):
        project = QgsProject.instance()
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            lyr_id = name_item.data(Qt.UserRole)
            lyr = project.mapLayer(lyr_id)
            if lyr and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                name_item.setCheckState(Qt.Checked)
                self.selected_layer_ids.add(lyr_id)
        self.table.blockSignals(False)

    def _clear_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            name_item.setCheckState(Qt.Unchecked)
        self.selected_layer_ids.clear()
        self.table.blockSignals(False)

    def get_results(self) -> (Set[str], bool):
        return set(self.selected_layer_ids), self.chk_include_active.isChecked()
