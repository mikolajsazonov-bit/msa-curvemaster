#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Moduł algorytmów offsetu dla geometrii wektorowych QGIS.
Autor: Mikołaj Sazonov
"""

import math
from typing import Tuple, Optional
from qgis.core import (
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    Qgis
)


def compute_line_offset(
    geom: QgsGeometry,
    cursor_pt: QgsPointXY,
    custom_distance: Optional[float] = None,
    miter_limit: float = 2.0
) -> Tuple[QgsGeometry, float, float]:
    """
    Oblicza równoległe odsunięcie (offset) dla linii lub polilinii.
    Strona odsunięcia (lewa/prawa) określana jest na podstawie pozycji cursor_pt względem geometrii.
    Zwraca krotkę: (offset_geom, odległość_bezwzględna, odległość_ze_znakiem).
    """
    if geom.isEmpty():
        return QgsGeometry(), 0.0, 0.0

    sqr_dist, min_pt, after_v, left_of = geom.closestSegmentWithContext(cursor_pt)
    measured_dist = math.sqrt(sqr_dist)
    dist = abs(custom_distance) if custom_distance is not None else measured_dist

    # W offsetCurve: dystans dodatni oznacza odsunięcie w lewo, ujemny w prawo
    signed_dist = dist if left_of < 0 else -dist

    if dist < 1e-6:
        return QgsGeometry(geom), 0.0, 0.0

    off = geom.offsetCurve(signed_dist, 8, Qgis.JoinStyle.Miter, miter_limit)
    if off.isNull() or off.isEmpty():
        off = geom.offsetCurve(signed_dist, 8, Qgis.JoinStyle.Round, miter_limit)

    return off, dist, signed_dist


def compute_polygon_offset(
    geom: QgsGeometry,
    cursor_pt: QgsPointXY,
    custom_distance: Optional[float] = None,
    miter_limit: float = 2.0
) -> Tuple[QgsGeometry, float, float]:
    """
    Oblicza równoległe odsunięcie (offset / bufor krawędzi) dla poligonu.
    Jeśli cursor_pt znajduje się wewnątrz poligonu, wykonuje bufor ujemny (do wewnątrz).
    Jeśli cursor_pt znajduje się na zewnątrz, wykonuje bufor dodatni (na zewnątrz).
    Zwraca krotkę: (offset_geom, odległość_bezwzględna, odległość_ze_znakiem).
    """
    if geom.isEmpty():
        return QgsGeometry(), 0.0, 0.0

    # Wyodrębnienie pierścieni zewnętrznych do precyzyjnego pomiaru odległości do krawędzi
    boundary = QgsGeometry()
    if geom.isMultipart():
        lines = []
        for poly in geom.asMultiPolygon():
            if poly:
                lines.append(poly[0])
        boundary = QgsGeometry.fromMultiPolylineXY(lines)
    else:
        rings = geom.asPolygon()
        if rings:
            boundary = QgsGeometry.fromPolylineXY(rings[0])

    if not boundary.isEmpty():
        sqr_dist, min_pt, after_v, left_of = boundary.closestSegmentWithContext(cursor_pt)
        measured_dist = math.sqrt(sqr_dist)
    else:
        measured_dist = geom.distance(QgsGeometry.fromPointXY(cursor_pt))

    dist = abs(custom_distance) if custom_distance is not None else measured_dist
    is_inside = geom.contains(cursor_pt)

    # Ujemny bufor zmniejsza poligon (do wewnątrz), dodatni powiększa (na zewnątrz)
    signed_dist = -dist if is_inside else dist

    if dist < 1e-6:
        return QgsGeometry(geom), 0.0, 0.0

    off = geom.buffer(signed_dist, 8, Qgis.EndCapStyle.Flat, Qgis.JoinStyle.Miter, miter_limit)
    if off.isNull() or off.isEmpty():
        off = geom.buffer(signed_dist, 8, Qgis.EndCapStyle.Flat, Qgis.JoinStyle.Round, miter_limit)

    return off, dist, signed_dist


def extract_rings_as_line(geom: QgsGeometry) -> QgsGeometry:
    """
    Wyciąga pierścienie poligonu jako geometrię liniową (LineString lub MultiLineString).
    """
    if geom.isEmpty():
        return QgsGeometry()

    if geom.isMultipart():
        lines = []
        for poly in geom.asMultiPolygon():
            for ring in poly:
                lines.append(ring)
        return QgsGeometry.fromMultiPolylineXY(lines)
    else:
        rings = geom.asPolygon()
        if not rings:
            return QgsGeometry()
        if len(rings) == 1:
            return QgsGeometry.fromPolylineXY(rings[0])
        else:
            return QgsGeometry.fromMultiPolylineXY(rings)
