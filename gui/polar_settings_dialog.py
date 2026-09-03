#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Okno dialogowe ustawień Polar Trackingu (CAD Drafting Settings).
Autor: Mikołaj Sazonov
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QCheckBox,
    QComboBox,
    QListWidget,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QDialogButtonBox,
    QLabel,
    QDoubleSpinBox
)
try:
    from ..core.polar_state import (
        PolarState,
        PolarAngleMeasurement,
        POLAR_INCREMENT_PRESETS,
        format_preset_label
    )
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.polar_state import (
        PolarState,
        PolarAngleMeasurement,
        POLAR_INCREMENT_PRESETS,
        format_preset_label
    )
    from core.i18n import tr


class PolarSettingsDialog(QDialog):
    """
    Okno dialogowe ustawień śledzenia biegunowego wzorowane na AutoCAD Drafting Settings.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = PolarState.instance()
        self.setWindowTitle(tr("Polar Tracking Settings", "Ustawienia śledzenia biegunowego"))
        self.setMinimumWidth(440)
        self._init_ui()
        self._load_from_state()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # 1. Główny przełącznik Polar Tracking On/Off
        self.chk_enabled = QCheckBox(tr("Polar Tracking On", "Włącz śledzenie biegunowe (Polar Tracking On)"))
        self.chk_enabled.setStyleSheet("font-weight: bold; font-size: 13px;")
        main_layout.addWidget(self.chk_enabled)

        grid_layout = QHBoxLayout()

        # 2. Grupa kątów (Lewa kolumna)
        grp_angles = QGroupBox(tr("Polar Angle Settings", "Ustawienia kątów (Polar Angle Settings)"))
        vbox_angles = QVBoxLayout(grp_angles)
        vbox_angles.setSpacing(10)

        # Krok kąta (Increment angle)
        h_inc = QHBoxLayout()
        lbl_inc = QLabel(tr("Increment angle:", "Krok kąta:"))
        self.combo_increment = QComboBox()
        for step in POLAR_INCREMENT_PRESETS:
            self.combo_increment.addItem(format_preset_label(step), step)
        h_inc.addWidget(lbl_inc)
        h_inc.addWidget(self.combo_increment, 1)
        vbox_angles.addLayout(h_inc)

        # Dodatkowe kąty (Additional angles)
        self.chk_additional = QCheckBox(tr("Additional angles", "Dodatkowe kąty (Additional angles)"))
        vbox_angles.addWidget(self.chk_additional)

        h_list = QHBoxLayout()
        self.list_angles = QListWidget()
        self.list_angles.setMaximumHeight(140)
        h_list.addWidget(self.list_angles, 1)

        v_btns = QVBoxLayout()
        self.spin_new_angle = QDoubleSpinBox()
        self.spin_new_angle.setRange(0.01, 359.99)
        self.spin_new_angle.setDecimals(2)
        self.spin_new_angle.setSuffix("°")
        self.spin_new_angle.setValue(147.0)

        self.btn_add = QPushButton(tr("Add", "Dodaj"))
        self.btn_add.clicked.connect(self._on_add_angle)
        self.btn_delete = QPushButton(tr("Delete", "Usuń"))
        self.btn_delete.clicked.connect(self._on_delete_angle)

        v_btns.addWidget(self.spin_new_angle)
        v_btns.addWidget(self.btn_add)
        v_btns.addWidget(self.btn_delete)
        v_btns.addStretch()
        h_list.addLayout(v_btns)

        vbox_angles.addLayout(h_list)
        grid_layout.addWidget(grp_angles, 3)

        # 3. Prawa kolumna (Measurement: Relative vs Absolute)
        grp_measure = QGroupBox(tr("Polar Angle Measurement", "Pomiar kąta polarnego (Measurement)"))
        vbox_measure = QVBoxLayout(grp_measure)
        vbox_measure.setSpacing(10)

        self.radio_absolute = QRadioButton(tr(
            "Absolute\n(to map coordinate system)",
            "Kąt bezwzględny (Absolute)\n(układ współrzędnych / ekran)"
        ))
        self.radio_relative = QRadioButton(tr(
            "Relative\n(to previous segment / starting edge)",
            "Kąt względny (Relative)\n(do krawędzi początkowej / segmentu)"
        ))

        self.btn_group_mode = QButtonGroup(self)
        self.btn_group_mode.addButton(self.radio_absolute, 0)
        self.btn_group_mode.addButton(self.radio_relative, 1)

        vbox_measure.addWidget(self.radio_absolute)
        vbox_measure.addWidget(self.radio_relative)
        vbox_measure.addStretch()

        grid_layout.addWidget(grp_measure, 2)
        main_layout.addLayout(grid_layout)

        # 4. Przyciski akcji
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_save_and_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _load_from_state(self):
        self.chk_enabled.setChecked(self.state.enabled)

        # Zaznacz bieżący krok
        current_step = self.state.increment_angle
        idx = self.combo_increment.findData(current_step)
        if idx >= 0:
            self.combo_increment.setCurrentIndex(idx)

        self.chk_additional.setChecked(self.state.additional_angles_enabled)
        self.list_angles.clear()
        for a in self.state.additional_angles:
            self.list_angles.addItem(f"{a:.2f}°")

        if self.state.measurement_mode == PolarAngleMeasurement.ABSOLUTE:
            self.radio_absolute.setChecked(True)
        else:
            self.radio_relative.setChecked(True)

    def _on_add_angle(self):
        val = self.spin_new_angle.value()
        # Sprawdź czy już istnieje
        existing = [float(self.list_angles.item(i).text().replace('°', '')) for i in range(self.list_angles.count())]
        if val not in existing:
            self.list_angles.addItem(f"{val:.2f}°")
            self.chk_additional.setChecked(True)

    def _on_delete_angle(self):
        row = self.list_angles.currentRow()
        if row >= 0:
            self.list_angles.takeItem(row)

    def _on_save_and_accept(self):
        self.state.enabled = self.chk_enabled.isChecked()

        idx = self.combo_increment.currentIndex()
        if idx >= 0:
            self.state.increment_angle = float(self.combo_increment.itemData(idx))

        self.state.additional_angles_enabled = self.chk_additional.isChecked()
        angles = []
        for i in range(self.list_angles.count()):
            try:
                angles.append(float(self.list_angles.item(i).text().replace('°', '')))
            except ValueError:
                pass
        self.state.additional_angles = angles

        if self.radio_absolute.isChecked():
            self.state.measurement_mode = PolarAngleMeasurement.ABSOLUTE
        else:
            self.state.measurement_mode = PolarAngleMeasurement.RELATIVE

        self.accept()
