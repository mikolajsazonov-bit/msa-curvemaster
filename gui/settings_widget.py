#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Kompaktowy pasek ustawień parametrów wtyczki.
Autor: Mikołaj Sazonov
"""

from typing import Optional, List, Dict, Any
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QCheckBox,
    QFrame,
    QMenu,
    QWidgetAction,
    QToolButton
)
try:
    from ..core.geometry_utils import SamplingMode
    from ..core.polar_state import PolarState, PolarAngleMeasurement, POLAR_INCREMENT_PRESETS
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.geometry_utils import SamplingMode
    from core.polar_state import PolarState, PolarAngleMeasurement, POLAR_INCREMENT_PRESETS
    from core.i18n import tr


class CurveSettingsWidget(QWidget):
    """
    Kompaktowy widget paska narzędzi zawierający kontrolki do wyboru trybu próbkowania łuków,
    kroku podziału oraz parametrów zaokrąglania narożników.
    Może dynamicznie rozwijać się w zależności od aktywnego narzędzia.
    """

    settingsChanged = pyqtSignal()
    pourCategoryChanged = pyqtSignal(str)
    pourLayersDialogRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode: Optional[str] = None
        self._init_ui()
        # Domyślnie widget jest zwinięty/ukryty na pasku narzędzi
        self.hide()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(2, 0, 2, 0)
        main_layout.setSpacing(4)

        # Kontener próbkowania (używany zarówno przy wyginaniu, jak i zaokrąglaniu)
        self.sampling_container = QWidget(self)
        samp_layout = QHBoxLayout(self.sampling_container)
        samp_layout.setContentsMargins(0, 0, 0, 0)
        samp_layout.setSpacing(4)

        lbl_mode = QLabel(tr("Sampling:", "Próbkowanie:"))
        lbl_mode.setStyleSheet("font-weight: 500; font-size: 11px;")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(tr("Linear step (m)", "Krok lin. (m)"), SamplingMode.LINEAR_STEP)
        self.combo_mode.addItem(tr("Angular step (°)", "Krok kąt. (°)"), SamplingMode.ANGULAR_STEP)
        self.combo_mode.addItem(tr("Max sagitta (m)", "Strzałka (m)"), SamplingMode.MAX_SAGITTA)
        self.combo_mode.setToolTip(tr(
            "Arc discretization method:\n- Linear: constant chord length (m)\n- Angular: central angle division (°)\n- Sagitta: max arc-chord deviation (m)",
            "Metoda dyskretyzacji łuku na proste odcinki:\n- Krok lin.: stała długość cięciwy (m)\n- Krok kąt.: podział kąta środkowego (°)\n- Strzałka: maks. odchyłka cięciwy od okręgu (m)"
        ))
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        self.spin_step = QDoubleSpinBox()
        self.spin_step.setDecimals(2)
        self.spin_step.setRange(0.01, 10000.0)
        self.spin_step.setValue(1.0)
        self.spin_step.setSuffix(" m")
        self.spin_step.setToolTip(tr("Sampling step value for selected mode", "Wartość kroku próbkowania dla wybranego trybu"))
        self.spin_step.valueChanged.connect(lambda: self.settingsChanged.emit())

        samp_layout.addWidget(lbl_mode)
        samp_layout.addWidget(self.combo_mode)
        samp_layout.addWidget(self.spin_step)
        main_layout.addWidget(self.sampling_container)

        # Kontener zaokrąglania narożników (widoczny tylko przy narzędziu Fillet)
        self.fillet_container = QWidget(self)
        fillet_layout = QHBoxLayout(self.fillet_container)
        fillet_layout.setContentsMargins(0, 0, 0, 0)
        fillet_layout.setSpacing(4)

        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.VLine)
        self.sep.setFrameShadow(QFrame.Sunken)
        fillet_layout.addWidget(self.sep)

        lbl_fillet = QLabel(tr("Radius:", "Promień:"))
        lbl_fillet.setStyleSheet("font-weight: 500; font-size: 11px;")
        self.spin_radius = QDoubleSpinBox()
        self.spin_radius.setDecimals(2)
        self.spin_radius.setRange(0.05, 10000.0)
        self.spin_radius.setValue(5.0)
        self.spin_radius.setSuffix(" m")
        self.spin_radius.setToolTip(tr("Corner fillet radius", "Promień zaokrąglenia narożnika (fillet)"))
        self.spin_radius.valueChanged.connect(lambda: self.settingsChanged.emit())

        self.chk_interactive = QCheckBox(tr("Interactive", "Interaktywny"))
        self.chk_interactive.setChecked(True)
        self.chk_interactive.setToolTip(tr(
            "Check to dynamically set radius with mouse and CAD HUD overlay.\nUncheck to use fixed radius from input box.",
            "Zaznacz, aby dynamicznie ustalać promień myszą i okienkiem CAD.\nOdznacz, aby zaokrąglać stałą wartością promienia z pola obok."
        ))
        self.chk_interactive.toggled.connect(self._on_interactive_toggled)

        fillet_layout.addWidget(lbl_fillet)
        fillet_layout.addWidget(self.spin_radius)
        fillet_layout.addWidget(self.chk_interactive)
        main_layout.addWidget(self.fillet_container)

        # Kontener polar trackingu (widoczny przy narzędziu PolarDigitizeTool)
        self.polar_container = QWidget(self)
        polar_layout = QHBoxLayout(self.polar_container)
        polar_layout.setContentsMargins(0, 0, 0, 0)
        polar_layout.setSpacing(4)

        lbl_polar_inc = QLabel(tr("Step:", "Krok:"))
        lbl_polar_inc.setStyleSheet("font-weight: 500; font-size: 11px;")
        self.combo_polar_inc = QComboBox()
        for step in POLAR_INCREMENT_PRESETS:
            self.combo_polar_inc.addItem(f"{step:g}°", step)
        self.combo_polar_inc.setToolTip(tr("Polar tracking increment angle", "Krok kątowy przyciągania polarnego"))
        self.combo_polar_inc.currentIndexChanged.connect(self._on_polar_inc_changed)

        self.combo_polar_mode = QComboBox()
        self.combo_polar_mode.addItem(tr("Relative", "Względny"), PolarAngleMeasurement.RELATIVE)
        self.combo_polar_mode.addItem(tr("Absolute", "Bezwzględny"), PolarAngleMeasurement.ABSOLUTE)
        self.combo_polar_mode.setToolTip(tr(
            "Angle measurement base:\n- Relative: to previous segment / starting edge\n- Absolute: to map coordinate system",
            "Baza pomiaru kąta:\n- Względny: do poprzedniego segmentu / krawędzi początkowej\n- Bezwzględny: do układu współrzędnych"
        ))
        self.combo_polar_mode.currentIndexChanged.connect(self._on_polar_measurement_changed)

        self.btn_polar_settings = QToolButton()
        self.btn_polar_settings.setText("⚙")
        self.btn_polar_settings.setToolTip(tr(
            "Open Polar Tracking settings (custom angles & options)",
            "Otwórz okno zaawansowanych ustawień Polar Trackingu (własne kąty)"
        ))
        self.btn_polar_settings.clicked.connect(self._open_polar_dialog)

        polar_layout.addWidget(lbl_polar_inc)
        polar_layout.addWidget(self.combo_polar_inc)
        polar_layout.addWidget(self.combo_polar_mode)
        polar_layout.addWidget(self.btn_polar_settings)
        main_layout.addWidget(self.polar_container)

        # Kontener wylewania nawierzchni (Smart Pour)
        self.pour_container = QWidget(self)
        pour_layout = QHBoxLayout(self.pour_container)
        pour_layout.setContentsMargins(0, 0, 0, 0)
        pour_layout.setSpacing(4)

        lbl_pour = QLabel(tr("Surface:", "Nawierzchnia:"))
        lbl_pour.setStyleSheet("font-weight: 500; font-size: 11px;")
        self.combo_pour_category = QComboBox()
        self.combo_pour_category.setMinimumWidth(120)
        self.combo_pour_category.setToolTip(tr(
            "Active surface category to pour (auto-merges touching polygons of same category).\nUse Tab while drawing to cycle categories.",
            "Aktywna kategoria nawierzchni (automatycznie scala stykające się poligony tej samej kategorii).\nKlawisz Tab w trakcie rysowania przełącza kategorie."
        ))
        self.combo_pour_category.currentTextChanged.connect(self._on_pour_category_changed)

        self.btn_pour_layers = QToolButton()
        self.btn_pour_layers.setText(tr("Edges...", "Krawędzie..."))
        self.btn_pour_layers.setToolTip(tr(
            "Select project layers that act as boundaries for pouring (curbs, borders)",
            "Wskaż warstwy projektu stanowiące krawędzie/granice dla wylewania nawierzchni"
        ))
        self.btn_pour_layers.clicked.connect(lambda: self.pourLayersDialogRequested.emit())

        pour_layout.addWidget(lbl_pour)
        pour_layout.addWidget(self.combo_pour_category)
        pour_layout.addWidget(self.btn_pour_layers)
        main_layout.addWidget(self.pour_container)

    def set_tool_mode(self, mode: Optional[str]):
        """
        Zmienia tryb wyświetlania paska w zależności od aktywnego narzędzia:
        - 'bend': rozwija tylko opcje próbkowania
        - 'fillet': rozwija opcje próbkowania oraz parametry zaokrąglania
        - 'polar': rozwija opcje kroku kąta i bazy pomiaru polarnego
        - 'pour': rozwija opcje kategorii nawierzchni Smart Pour
        - None / 'none': zwija/ukrywa cały panel ustawień z paska narzędzi
        """
        self._current_mode = mode
        if mode == 'bend':
            self.sampling_container.setVisible(True)
            self.fillet_container.setVisible(False)
            self.polar_container.setVisible(False)
            self.pour_container.setVisible(False)
            self.setVisible(True)
        elif mode in ('fillet', 'fillet_lines'):
            self.sampling_container.setVisible(True)
            self.fillet_container.setVisible(True)
            self.polar_container.setVisible(False)
            self.pour_container.setVisible(False)
            self.setVisible(True)
        elif mode == 'polar':
            self.sampling_container.setVisible(False)
            self.fillet_container.setVisible(False)
            self.polar_container.setVisible(True)
            self.pour_container.setVisible(False)
            self._sync_polar_ui_from_state()
            self.setVisible(True)
        elif mode == 'pour':
            self.sampling_container.setVisible(False)
            self.fillet_container.setVisible(False)
            self.polar_container.setVisible(False)
            self.pour_container.setVisible(True)
            self.setVisible(True)
        else:
            self.setVisible(False)

    def _sync_polar_ui_from_state(self):
        state = PolarState.instance()
        idx_inc = self.combo_polar_inc.findData(state.increment_angle)
        if idx_inc >= 0:
            self.combo_polar_inc.blockSignals(True)
            self.combo_polar_inc.setCurrentIndex(idx_inc)
            self.combo_polar_inc.blockSignals(False)

        idx_mode = self.combo_polar_mode.findData(state.measurement_mode)
        if idx_mode >= 0:
            self.combo_polar_mode.blockSignals(True)
            self.combo_polar_mode.setCurrentIndex(idx_mode)
            self.combo_polar_mode.blockSignals(False)

    def _on_polar_inc_changed(self, index: int):
        val = self.combo_polar_inc.itemData(index)
        if val is not None:
            PolarState.instance().increment_angle = float(val)

    def _on_polar_measurement_changed(self, index: int):
        val = self.combo_polar_mode.itemData(index)
        if val is not None:
            PolarState.instance().measurement_mode = val

    def _open_polar_dialog(self):
        try:
            from .polar_settings_dialog import PolarSettingsDialog
        except (ImportError, ValueError):
            from gui.polar_settings_dialog import PolarSettingsDialog
        dlg = PolarSettingsDialog(self)
        if dlg.exec_():
            self._sync_polar_ui_from_state()

    def _on_mode_changed(self, index: int):
        mode = self.combo_mode.itemData(index)
        if mode == SamplingMode.LINEAR_STEP:
            self.spin_step.setSuffix(" m")
            self.spin_step.setDecimals(2)
            self.spin_step.setRange(0.05, 1000.0)
            self.spin_step.setValue(1.0)
        elif mode == SamplingMode.ANGULAR_STEP:
            self.spin_step.setSuffix(" °")
            self.spin_step.setDecimals(1)
            self.spin_step.setRange(0.5, 90.0)
            self.spin_step.setValue(5.0)
        elif mode == SamplingMode.MAX_SAGITTA:
            self.spin_step.setSuffix(" m")
            self.spin_step.setDecimals(3)
            self.spin_step.setRange(0.001, 10.0)
            self.spin_step.setValue(0.02)

        self.settingsChanged.emit()

    def _on_interactive_toggled(self, checked: bool):
        self.spin_radius.setEnabled(not checked)
        self.settingsChanged.emit()

    def sampling_mode(self) -> SamplingMode:
        return self.combo_mode.currentData()

    def step_value(self) -> float:
        return self.spin_step.value()

    def fillet_radius(self) -> float:
        return self.spin_radius.value()

    def is_interactive_fillet(self) -> bool:
        return self.chk_interactive.isChecked()

    def create_dropdown_menu(self, tool_name: str, parent=None) -> QMenu:
        """
        Tworzy rozwijane menu (popup menu dla QToolButton.MenuButtonPopup)
        umożliwiające szybki wybór metody próbkowania i wartości.
        """
        menu = QMenu(parent or self)
        menu.setTitle(tr("Sampling Settings", "Ustawienia próbkowania"))

        # Tytuł sekcji próbkowania
        lbl_header = QLabel(tr("  Arc sampling method:", "  Metoda próbkowania łuku:"))
        lbl_header.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
        act_header = QWidgetAction(menu)
        act_header.setDefaultWidget(lbl_header)
        menu.addAction(act_header)

        # Opcje wyboru trybu
        modes = [
            (tr("Chord length (m)", "Długość odcinka (m)"), SamplingMode.LINEAR_STEP),
            (tr("Angular step (°)", "Krok kątowy (°)"), SamplingMode.ANGULAR_STEP),
            (tr("Max sagitta (m)", "Odchyłka/Strzałka (m)"), SamplingMode.MAX_SAGITTA),
        ]

        mode_actions = []
        for label, smode in modes:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.sampling_mode() == smode)
            # Obsługa kliknięcia w menu
            def make_handler(m=smode):
                return lambda: self._set_mode_from_menu(m)
            act.triggered.connect(make_handler(smode))
            mode_actions.append((act, smode))

        act_inter = None
        if tool_name == 'fillet':
            menu.addSeparator()
            lbl_fillet_hdr = QLabel(tr("  Fillet options:", "  Parametry zaokrąglenia:"))
            lbl_fillet_hdr.setStyleSheet("font-weight: bold; color: #6c757d; font-size: 11px; padding: 4px 6px;")
            act_fillet_hdr = QWidgetAction(menu)
            act_fillet_hdr.setDefaultWidget(lbl_fillet_hdr)
            menu.addAction(act_fillet_hdr)

            act_inter = menu.addAction(tr("Interactive mode (mouse + CAD)", "Tryb interaktywny (mysz + CAD)"))
            act_inter.setCheckable(True)
            act_inter.setChecked(self.is_interactive_fillet())
            act_inter.toggled.connect(self.chk_interactive.setChecked)

        def on_about_to_show():
            curr_m = self.sampling_mode()
            for a, sm in mode_actions:
                a.setChecked(curr_m == sm)
            if act_inter is not None:
                act_inter.setChecked(self.is_interactive_fillet())

        menu.aboutToShow.connect(on_about_to_show)
        return menu

    def _set_mode_from_menu(self, smode: SamplingMode):
        idx = self.combo_mode.findData(smode)
        if idx >= 0:
            self.combo_mode.setCurrentIndex(idx)

    def _on_pour_category_changed(self, text: str):
        self.pourCategoryChanged.emit(text)

    def set_pour_categories(
        self,
        categories: List[str],
        active: Optional[str] = None,
        category_styles: Optional[Dict[str, Any]] = None
    ):
        """Ustawia listę dostępnych kategorii w liście rozwijanej wraz z próbkami stylizacji z warstwy."""
        self.combo_pour_category.blockSignals(True)
        self.combo_pour_category.clear()
        for cat in categories:
            icon = None
            if category_styles:
                style = category_styles.get(cat) or category_styles.get(cat.lower())
                if style and hasattr(style, 'get_icon'):
                    icon = style.get_icon(16)
            if icon and not icon.isNull():
                self.combo_pour_category.addItem(icon, cat)
            else:
                self.combo_pour_category.addItem(cat)

        # Opcja dodania nowej kategorii
        self.combo_pour_category.addItem(tr("[+ New Category...]", "[➕ Nowa kategoria...]"))

        if active:
            idx = self.combo_pour_category.findText(active)
            if idx >= 0:
                self.combo_pour_category.setCurrentIndex(idx)
            elif self.combo_pour_category.count() > 0:
                self.combo_pour_category.setCurrentIndex(0)
        elif self.combo_pour_category.count() > 0:
            self.combo_pour_category.setCurrentIndex(0)
        self.combo_pour_category.blockSignals(False)

    def current_pour_category(self) -> str:
        return self.combo_pour_category.currentText()

    def set_current_pour_category(self, name: str, style: Optional[Any] = None):
        idx = self.combo_pour_category.findText(name)
        if idx >= 0:
            self.combo_pour_category.setCurrentIndex(idx)
        else:
            pos = max(0, self.combo_pour_category.count() - 1)
            icon = style.get_icon(16) if (style and hasattr(style, 'get_icon')) else None
            if icon and not icon.isNull():
                self.combo_pour_category.insertItem(pos, icon, name)
            else:
                self.combo_pour_category.insertItem(pos, name)
            self.combo_pour_category.setCurrentIndex(pos)

    def cycle_pour_category(self, step: int = 1) -> str:
        """Przeskakuje do kolejnej kategorii (klawisz Tab)."""
        count = self.combo_pour_category.count()
        if count <= 0:
            return ""
        curr = self.combo_pour_category.currentIndex()
        next_idx = (curr + step) % count
        self.combo_pour_category.setCurrentIndex(next_idx)
        return self.combo_pour_category.currentText()

