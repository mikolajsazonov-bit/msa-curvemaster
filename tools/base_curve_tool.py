#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Klasa bazowa dla narzędzi mapowych edycji geometrii.
Autor: Mikołaj Sazonov
"""

from typing import Optional, Tuple, List
from qgis.PyQt.QtCore import Qt, QPoint
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.gui import (
    QgsMapToolEdit,
    QgsMapCanvas,
    QgsRubberBand,
    QgsMapMouseEvent
)
from qgis.core import (
    QgsVectorLayer,
    QgsWkbTypes,
    QgsPointXY,
    QgsGeometry,
    QgsPointLocator,
    QgsCoordinateTransform,
    QgsProject,
    QgsRectangle
)
from ..gui.settings_widget import CurveSettingsWidget
from ..core.geometry_utils import Point2D


class BaseCurveTool(QgsMapToolEdit):
    """
    Bazowa klasa narzędzia mapy dla operacji na krzywych i łukach.
    Obsługuje transformacje układów współrzędnych (CRS) między płótnem mapy a edytowaną warstwą.
    """

    def __init__(self, canvas: QgsMapCanvas, settings_widget: CurveSettingsWidget):
        super().__init__(canvas)
        self._canvas = canvas
        self._settings = settings_widget
        self.settings_widget = settings_widget

        # Gumki podglądu (RubberBands)
        self.preview_band = QgsRubberBand(self._canvas, QgsWkbTypes.LineGeometry)
        self.preview_band.setColor(QColor(230, 30, 30, 220))
        self.preview_band.setWidth(3)

        self.highlight_band = QgsRubberBand(self._canvas, QgsWkbTypes.PointGeometry)
        self.highlight_band.setColor(QColor(0, 150, 255, 200))
        self.highlight_band.setIcon(QgsRubberBand.ICON_CIRCLE)
        self.highlight_band.setIconSize(10)

        self.setCursor(QCursor(Qt.CrossCursor))

    def settings(self) -> CurveSettingsWidget:
        return self._settings

    def active_editable_layer(self) -> Optional[QgsVectorLayer]:
        """Zwraca aktywną warstwę jeśli jest wektorowa, edytowalna i typu linia/poligon."""
        layer = self._canvas.currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            return None
        if not layer.isEditable():
            return None
        geom_type = layer.geometryType()
        if geom_type not in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
            return None
        return layer

    def to_layer_point(self, layer: QgsVectorLayer, canvas_pt: QgsPointXY) -> QgsPointXY:
        """Konwertuje punkt z układu płótna (canvas CRS) do układu warstwy (layer CRS)."""
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs == layer_crs or not layer_crs.isValid() or not canvas_crs.isValid():
            return QgsPointXY(canvas_pt)
        try:
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            return transform.transform(canvas_pt)
        except Exception:
            return QgsPointXY(canvas_pt)

    def to_canvas_point(self, layer: QgsVectorLayer, layer_pt: QgsPointXY) -> QgsPointXY:
        """Konwertuje punkt z układu warstwy (layer CRS) do układu płótna (canvas CRS)."""
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs == layer_crs or not layer_crs.isValid() or not canvas_crs.isValid():
            return QgsPointXY(layer_pt)
        try:
            transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            return transform.transform(layer_pt)
        except Exception:
            return QgsPointXY(layer_pt)

    def to_layer_rect(self, layer: QgsVectorLayer, canvas_rect: QgsRectangle) -> QgsRectangle:
        """Konwertuje prostokąt z układu płótna (canvas CRS) do układu warstwy (layer CRS)."""
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs == layer_crs or not layer_crs.isValid() or not canvas_crs.isValid():
            return QgsRectangle(canvas_rect)
        try:
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            return transform.transformBoundingBox(canvas_rect)
        except Exception:
            return QgsRectangle(canvas_rect)

    def to_canvas_points_list(self, layer: QgsVectorLayer, pts: List[Point2D]) -> List[QgsPointXY]:
        """Konwertuje listę punktów (x, y) z układu warstwy do listy QgsPointXY w układzie płótna."""
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs == layer_crs or not layer_crs.isValid() or not canvas_crs.isValid():
            return [QgsPointXY(p[0], p[1]) for p in pts]
        try:
            transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            return [transform.transform(QgsPointXY(p[0], p[1])) for p in pts]
        except Exception:
            return [QgsPointXY(p[0], p[1]) for p in pts]

    def snap_point(self, e: QgsMapMouseEvent, match_type=QgsPointLocator.All) -> Tuple[QgsPointXY, Optional[QgsPointLocator.Match]]:
        """Przyciąga punkt kursora zgodnie z globalnymi ustawieniami przyciągania QGIS (w CRS mapy)."""
        match = self._canvas.snappingUtils().snapToMap(e.pos())
        if match.isValid():
            return match.point(), match
        return e.mapPoint(), None

    def snap_point_layer(self, e: QgsMapMouseEvent, layer: Optional[QgsVectorLayer] = None) -> Tuple[QgsPointXY, QgsPointXY]:
        """
        Zwraca krotkę (canvas_point, layer_point).
        canvas_point jest w CRS mapy/płótna, layer_point w CRS warstwy.
        """
        canvas_pt, _ = self.snap_point(e)
        if layer:
            layer_pt = self.to_layer_point(layer, canvas_pt)
        else:
            layer_pt = canvas_pt
        return canvas_pt, layer_pt

    def clear_preview(self):
        """Czyści podglądy na płótnie mapy."""
        if self.preview_band:
            self.preview_band.reset(QgsWkbTypes.LineGeometry)
        if self.highlight_band:
            self.highlight_band.reset(QgsWkbTypes.PointGeometry)

    def deactivate(self):
        self.clear_preview()
        super().deactivate()

