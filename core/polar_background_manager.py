#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Asystent Polar Trackingu w tle dla narzędzi QGIS.
Autor: Mikołaj Sazonov
"""

from typing import Optional
from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QAction
from .polar_state import PolarState, PolarAngleMeasurement


class PolarBackgroundManager(QObject):
    """
    Mostek synchronizujący stan PolarState z wbudowanym mechanizmem
    Zaawansowanej Digitalizacji QGIS (QgsAdvancedDigitizingDockWidget).
    Dzięki temu standardowe narzędzia QGIS (Rozdziel obiekty, Zmień kształt, Dodaj obiekt)
    korzystają z wybranego kroku kąta bez konieczności ręcznego konfigurowania panelu.
    """

    def __init__(self, iface=None, parent=None):
        if parent is not None and isinstance(parent, QObject):
            super().__init__(parent)
        else:
            super().__init__()
        self.iface = iface
        self.state = PolarState.instance()
        self.state.stateChanged.connect(self.sync_with_qgis_cad)

        if self.iface and hasattr(self.iface, 'mapCanvas') and self.iface.mapCanvas():
            self.iface.mapCanvas().mapToolSet.connect(self._on_map_tool_changed)

    def _get_cad_dock(self):
        """Pobiera instancję QgsAdvancedDigitizingDockWidget z interfejsu QGIS."""
        if self.iface and hasattr(self.iface, 'cadDockWidget'):
            return self.iface.cadDockWidget()
        return None

    def sync_with_qgis_cad(self):
        """Synchronizuje bieżący stan PolarState z dokiem Zaawansowanej Digitalizacji QGIS."""
        cad = self._get_cad_dock()
        if not cad:
            return

        # Włącz lub wyłącz tryb Zaawansowanej Digitalizacji (CAD) w QGIS
        act_enable = cad.enableAction()
        if self.state.enabled:
            if act_enable and not act_enable.isChecked():
                act_enable.trigger()
        else:
            if act_enable and act_enable.isChecked():
                act_enable.trigger()
            return

        mSettingsAction = cad.findChild(QAction, 'mSettingsAction')
        if not mSettingsAction or not mSettingsAction.menu():
            return

        menu = mSettingsAction.menu()

        # Jeśli włączony, wyszukaj akcję odpowiadającą zadanemu krokowi kątowemu
        target_step = self.state.increment_angle
        matched_act = None

        for act in menu.actions():
            txt = act.text()
            # Szukamy wartości np. "15.0" lub "15,"
            step_str_dot = f"{target_step:.1f}"
            step_str_int = f"{int(target_step)}" if float(target_step).is_integer() else None

            if step_str_dot in txt or (step_str_int and f"{step_str_int}," in txt) or (step_str_int and f"{step_str_int}." in txt):
                matched_act = act
                break

        if matched_act:
            if not matched_act.isChecked():
                matched_act.trigger()

    def _on_map_tool_changed(self, tool):
        """Reakcja na zmianę aktywnego narzędzia na mapie (np. włączenie Zmień kształt lub Rozdziel obiekty)."""
        if self.state.enabled:
            self.sync_with_qgis_cad()
