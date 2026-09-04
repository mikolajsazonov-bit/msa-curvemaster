#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
***************************************************************************
*   MSA: CurveMaster - Główna klasa wtyczki QGIS                          *
*   Autor: Mikołaj Sazonov                                                *
***************************************************************************
"""

import os
from typing import Optional
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QToolBar, QActionGroup, QToolButton
from qgis.core import QgsWkbTypes, QgsVectorLayer, QgsMessageLog, Qgis

from .gui.settings_widget import CurveSettingsWidget
from .tools.bend_segment_tool import BendSegmentTool
from .tools.corner_fillet_tool import CornerFilletTool
from .tools.two_line_fillet_tool import TwoLineFilletTool
from .tools.trim_extend_tool import TrimExtendTool
from .tools.offset_tool import OffsetTool
from .tools.polar_digitize_tool import PolarDigitizeTool
from .core.polar_background_manager import PolarBackgroundManager


class MSACurveMasterPlugin:
    """
    Główna klasa wtyczki MSA: CurveMaster dla QGIS 3.x.
    """

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)

        self.toolbar: QToolBar = None
        self.settings_widget: CurveSettingsWidget = None

        self.action_bend: QAction = None
        self.action_fillet: QAction = None
        self.action_fillet_lines: QAction = None
        self.action_trim_extend: QAction = None
        self.action_offset: QAction = None
        self.action_polar: QAction = None
        self.action_group: QActionGroup = None

        self.bend_tool: BendSegmentTool = None
        self.fillet_tool: CornerFilletTool = None
        self.fillet_lines_tool: TwoLineFilletTool = None
        self.trim_extend_tool: TrimExtendTool = None
        self.offset_tool: OffsetTool = None
        self.polar_tool: PolarDigitizeTool = None
        self.polar_bg_manager: PolarBackgroundManager = None

        self.btn_bend: QToolButton = None
        self.btn_fillet: QToolButton = None
        self.btn_fillet_lines: QToolButton = None
        self.btn_trim_extend: QToolButton = None
        self.btn_offset: QToolButton = None
        self.btn_polar: QToolButton = None

    def tr(self, message_en: str, message_pl: str = None) -> str:
        from .core.i18n import tr as i18n_tr
        return i18n_tr(message_en, message_pl, 'MSACurveMasterPlugin')

    def _load_icon(self, relative_path: str) -> QIcon:
        """Ładuje ikonę SVG lub PNG jeśli istnieje."""
        full_path = os.path.join(self.plugin_dir, relative_path)
        if os.path.exists(full_path):
            return QIcon(full_path)
        base, ext = os.path.splitext(full_path)
        alt_path = base + ('.svg' if ext == '.png' else '.png')
        if os.path.exists(alt_path):
            return QIcon(alt_path)
        return QIcon()

    def initGui(self):
        # 1. Pasek narzędzi
        self.toolbar = self.iface.addToolBar(self.tr('MSA: CurveMaster', 'MSA: CurveMaster'))
        self.toolbar.setObjectName('MSACurveMasterToolbar')

        # 2. Inicjalizacja widgetu ustawień (domyślnie zwinięty/ukryty)
        self.settings_widget = CurveSettingsWidget(self.iface.mainWindow())
        self.settings_widget.set_tool_mode('none')

        # 3. Inicjalizacja narzędzi mapowych
        self.bend_tool = BendSegmentTool(self.canvas, self.settings_widget)
        self.fillet_tool = CornerFilletTool(self.canvas, self.settings_widget, self.iface)
        self.fillet_lines_tool = TwoLineFilletTool(self.canvas, self.settings_widget, self.iface)
        self.trim_extend_tool = TrimExtendTool(self.canvas, self.settings_widget, self.iface)
        self.offset_tool = OffsetTool(self.canvas, self.settings_widget, self.iface)
        self.polar_tool = PolarDigitizeTool(self.canvas, self.settings_widget, self.iface)

        # 4. Asystent w tle (dla standardowych narzędzi QGIS)
        self.polar_bg_manager = PolarBackgroundManager(self.iface)

        # 5. Akcje narzędzi
        icon_bend = self._load_icon('icons/bend_segment.svg')
        self.action_bend = QAction(
            icon_bend,
            self.tr('Bend Segment to Arc', 'Wygnij odcinek w łuk'),
            self.iface.mainWindow()
        )
        self.action_bend.setCheckable(True)
        self.action_bend.setStatusTip(self.tr(
            'MSA: Drag a straight polyline or polygon segment into an arc',
            'MSA: Przeciągnij prosty odcinek polilinii/poligonu w zinterpolowany łuk'
        ))
        self.action_bend.triggered.connect(self._toggle_bend_tool)

        icon_fillet = self._load_icon('icons/corner_fillet.svg')
        self.action_fillet = QAction(
            icon_fillet,
            self.tr('Corner Fillet', 'Zaokrąglij wierzchołek'),
            self.iface.mainWindow()
        )
        self.action_fillet.setCheckable(True)
        self.action_fillet.setStatusTip(self.tr(
            'MSA: Round a sharp corner vertex with a tangent arc (CAD overlay)',
            'MSA: Zaokrąglij wierzchołek narożnika łukiem stycznym (CAD overlay)'
        ))
        self.action_fillet.triggered.connect(self._toggle_fillet_tool)

        icon_fillet_lines = self._load_icon('icons/fillet_lines.svg')
        self.action_fillet_lines = QAction(
            icon_fillet_lines,
            self.tr('Two-Line Fillet', 'Zaokrąglij dwie linie (Fillet)'),
            self.iface.mainWindow()
        )
        self.action_fillet_lines.setCheckable(True)
        self.action_fillet_lines.setStatusTip(self.tr(
            'MSA: Fillet between two lines with auto-trim and interactive CAD radius',
            'MSA: Zaokrąglij narożnik dwóch linii z automatycznym docięciem (Trim) i wprowadzaniem promienia'
        ))
        self.action_fillet_lines.triggered.connect(self._toggle_fillet_lines_tool)

        icon_trim_extend = self._load_icon('icons/trim_extend.svg')
        self.action_trim_extend = QAction(
            icon_trim_extend,
            self.tr('Trim / Extend', 'Utnij / Wydłuż (Trim / Extend)'),
            self.iface.mainWindow()
        )
        self.action_trim_extend.setCheckable(True)
        self.action_trim_extend.setStatusTip(self.tr(
            'MSA: Extend line on Click, Trim segment on Shift+Click',
            'MSA: Kliknij, aby wydłużyć linię (Extend), kliknij z Shiftem, aby przyciąć (Trim)'
        ))
        self.action_trim_extend.triggered.connect(self._toggle_trim_extend_tool)

        icon_offset = self._load_icon('icons/offset.svg')
        self.action_offset = QAction(
            icon_offset,
            self.tr('Offset Tool', 'Prosty offset'),
            self.iface.mainWindow()
        )
        self.action_offset.setCheckable(True)
        self.action_offset.setStatusTip(self.tr(
            'MSA: Parallel offset for lines and polygons (drag or type distance)',
            'MSA: Prosty offset linii, polilinii i granic poligonów (przeciągnij myszą lub wpisz odległość)'
        ))
        self.action_offset.triggered.connect(self._toggle_offset_tool)

        icon_polar = self._load_icon('icons/polar_tracking.svg')
        self.action_polar = QAction(
            icon_polar,
            self.tr('Polar Digitize', 'Rysuj z Polar Trackingiem'),
            self.iface.mainWindow()
        )
        self.action_polar.setCheckable(True)
        self.action_polar.setStatusTip(self.tr(
            'MSA: Draw lines and polygons with angle snapping (CAD Polar Tracking)',
            'MSA: Rysuj linie i poligony z przyciąganiem do kątów względnych i bezwzględnych (CAD Polar Tracking)'
        ))
        self.action_polar.triggered.connect(self._toggle_polar_tool)

        # Grupa akcji
        self.action_group = QActionGroup(self.iface.mainWindow())
        self.action_group.setExclusive(False)
        self.action_group.addAction(self.action_bend)
        self.action_group.addAction(self.action_fillet)
        self.action_group.addAction(self.action_fillet_lines)
        self.action_group.addAction(self.action_trim_extend)
        self.action_group.addAction(self.action_offset)
        self.action_group.addAction(self.action_polar)

        # 6. Przyciski QToolButton z rozwijanym menu (MenuButtonPopup)
        self.btn_bend = QToolButton(self.toolbar)
        self.btn_bend.setDefaultAction(self.action_bend)
        self.btn_bend.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_bend.setMenu(self.settings_widget.create_dropdown_menu('bend', self.btn_bend))

        self.btn_fillet = QToolButton(self.toolbar)
        self.btn_fillet.setDefaultAction(self.action_fillet)
        self.btn_fillet.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_fillet.setMenu(self.settings_widget.create_dropdown_menu('fillet', self.btn_fillet))

        self.btn_fillet_lines = QToolButton(self.toolbar)
        self.btn_fillet_lines.setDefaultAction(self.action_fillet_lines)
        self.btn_fillet_lines.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_fillet_lines.setMenu(self.fillet_lines_tool.create_dropdown_menu(self.btn_fillet_lines))

        self.btn_trim_extend = QToolButton(self.toolbar)
        self.btn_trim_extend.setDefaultAction(self.action_trim_extend)
        self.btn_trim_extend.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_trim_extend.setMenu(self.trim_extend_tool.create_dropdown_menu(self.btn_trim_extend))

        self.btn_offset = QToolButton(self.toolbar)
        self.btn_offset.setDefaultAction(self.action_offset)
        self.btn_offset.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_offset.setMenu(self.offset_tool.create_dropdown_menu(self.btn_offset))

        self.btn_polar = QToolButton(self.toolbar)
        self.btn_polar.setDefaultAction(self.action_polar)
        self.btn_polar.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_polar.setMenu(self.polar_tool.create_dropdown_menu(self.btn_polar))

        # 7. Dodanie kontrolek do paska narzędzi
        self.toolbar.addWidget(self.btn_bend)
        self.toolbar.addWidget(self.btn_fillet)
        self.toolbar.addWidget(self.btn_fillet_lines)
        self.toolbar.addWidget(self.btn_trim_extend)
        self.toolbar.addWidget(self.btn_offset)
        self.toolbar.addWidget(self.btn_polar)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.settings_widget)

        # 8. Menu Wektor
        self.iface.addPluginToVectorMenu(self.tr('MSA: CurveMaster'), self.action_bend)
        self.iface.addPluginToVectorMenu(self.tr('MSA: CurveMaster'), self.action_fillet)
        self.iface.addPluginToVectorMenu(self.tr('MSA: CurveMaster'), self.action_fillet_lines)
        self.iface.addPluginToVectorMenu(self.tr('MSA: CurveMaster'), self.action_trim_extend)
        self.iface.addPluginToVectorMenu(self.tr('MSA: CurveMaster'), self.action_offset)
        self.iface.addPluginToVectorMenu(self.tr('MSA: CurveMaster'), self.action_polar)

        # 9. Śledzenie zmiany narzędzia na płótnie mapy
        self.canvas.mapToolSet.connect(self._on_map_tool_changed)

    def unload(self):
        # Odłączenie sygnałów
        try:
            self.canvas.mapToolSet.disconnect(self._on_map_tool_changed)
        except Exception as err:
            QgsMessageLog.logMessage(f"MapToolSet disconnect: {err}", "MSA: CurveMaster", Qgis.Info)

        # Jeśli któreś z naszych narzędzi jest aktywne, zresetuj je
        curr_tool = self.canvas.mapTool()
        if curr_tool in (self.bend_tool, self.fillet_tool, self.fillet_lines_tool, self.trim_extend_tool, self.offset_tool, self.polar_tool):
            self.canvas.unsetMapTool(curr_tool)

        if self.bend_tool:
            self.bend_tool.clear_preview()
            self.bend_tool = None

        if self.fillet_tool:
            self.fillet_tool.clear_preview()
            self.fillet_tool = None

        if self.fillet_lines_tool:
            self.fillet_lines_tool.clear_preview()
            self.fillet_lines_tool = None

        if self.trim_extend_tool:
            self.trim_extend_tool.clear_preview()
            self.trim_extend_tool = None

        if self.offset_tool:
            self.offset_tool.clear_preview()
            self.offset_tool = None

        if self.polar_tool:
            self.polar_tool.clear_preview()
            self.polar_tool = None

        self.polar_bg_manager = None

        if self.action_bend:
            self.iface.removePluginVectorMenu(self.tr('MSA: CurveMaster'), self.action_bend)
            self.action_bend = None

        if self.action_fillet:
            self.iface.removePluginVectorMenu(self.tr('MSA: CurveMaster'), self.action_fillet)
            self.action_fillet = None

        if self.action_fillet_lines:
            self.iface.removePluginVectorMenu(self.tr('MSA: CurveMaster'), self.action_fillet_lines)
            self.action_fillet_lines = None

        if self.action_trim_extend:
            self.iface.removePluginVectorMenu(self.tr('MSA: CurveMaster'), self.action_trim_extend)
            self.action_trim_extend = None

        if self.action_offset:
            self.iface.removePluginVectorMenu(self.tr('MSA: CurveMaster'), self.action_offset)
            self.action_offset = None

        if self.action_polar:
            self.iface.removePluginVectorMenu(self.tr('MSA: CurveMaster'), self.action_polar)
            self.action_polar = None

        self.btn_bend = None
        self.btn_fillet = None
        self.btn_fillet_lines = None
        self.btn_trim_extend = None
        self.btn_offset = None
        self.btn_polar = None

        if self.toolbar:
            del self.toolbar
            self.toolbar = None

    def _uncheck_all_except(self, active_action: Optional[QAction]):
        actions = [
            self.action_bend,
            self.action_fillet,
            self.action_fillet_lines,
            self.action_trim_extend,
            self.action_offset,
            self.action_polar
        ]
        for act in actions:
            if act and act != active_action:
                act.setChecked(False)

    def _toggle_bend_tool(self, checked: bool):
        if checked:
            self._uncheck_all_except(self.action_bend)
            self.canvas.setMapTool(self.bend_tool)
        else:
            if self.canvas.mapTool() == self.bend_tool:
                self.canvas.unsetMapTool(self.bend_tool)

    def _toggle_fillet_tool(self, checked: bool):
        if checked:
            self._uncheck_all_except(self.action_fillet)
            self.canvas.setMapTool(self.fillet_tool)
        else:
            if self.canvas.mapTool() == self.fillet_tool:
                self.canvas.unsetMapTool(self.fillet_tool)

    def _toggle_fillet_lines_tool(self, checked: bool):
        if checked:
            self._uncheck_all_except(self.action_fillet_lines)
            self.canvas.setMapTool(self.fillet_lines_tool)
        else:
            if self.canvas.mapTool() == self.fillet_lines_tool:
                self.canvas.unsetMapTool(self.fillet_lines_tool)

    def _toggle_trim_extend_tool(self, checked: bool):
        if checked:
            self._uncheck_all_except(self.action_trim_extend)
            self.canvas.setMapTool(self.trim_extend_tool)
        else:
            if self.canvas.mapTool() == self.trim_extend_tool:
                self.canvas.unsetMapTool(self.trim_extend_tool)

    def _toggle_offset_tool(self, checked: bool):
        if checked:
            self._uncheck_all_except(self.action_offset)
            self.canvas.setMapTool(self.offset_tool)
        else:
            if self.canvas.mapTool() == self.offset_tool:
                self.canvas.unsetMapTool(self.offset_tool)

    def _toggle_polar_tool(self, checked: bool):
        if checked:
            self._uncheck_all_except(self.action_polar)
            self.canvas.setMapTool(self.polar_tool)
        else:
            if self.canvas.mapTool() == self.polar_tool:
                self.canvas.unsetMapTool(self.polar_tool)

    def _on_map_tool_changed(self, new_tool):
        if new_tool == self.bend_tool:
            self.action_bend.setChecked(True)
            self._uncheck_all_except(self.action_bend)
            self.settings_widget.set_tool_mode('bend')
        elif new_tool == self.fillet_tool:
            self.action_fillet.setChecked(True)
            self._uncheck_all_except(self.action_fillet)
            self.settings_widget.set_tool_mode('fillet')
        elif new_tool == self.fillet_lines_tool:
            self.action_fillet_lines.setChecked(True)
            self._uncheck_all_except(self.action_fillet_lines)
            self.settings_widget.set_tool_mode('fillet_lines')
        elif new_tool == self.trim_extend_tool:
            self.action_trim_extend.setChecked(True)
            self._uncheck_all_except(self.action_trim_extend)
            self.settings_widget.set_tool_mode('none')
        elif new_tool == self.offset_tool:
            self.action_offset.setChecked(True)
            self._uncheck_all_except(self.action_offset)
            self.settings_widget.set_tool_mode('none')
        elif new_tool == self.polar_tool:
            self.action_polar.setChecked(True)
            self._uncheck_all_except(self.action_polar)
            self.settings_widget.set_tool_mode('polar')
        else:
            self._uncheck_all_except(None)
            self.settings_widget.set_tool_mode('none')
