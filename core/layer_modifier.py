#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Modyfikator geometrii warstw QGIS z obsługą transakcji.
Autor: Mikołaj Sazonov
"""

from typing import List, Tuple, Optional
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes
)
from .geometry_utils import (
    Point2D,
    replace_segment_in_points,
    replace_vertex_in_points,
    replace_vertex_range_in_points
)


def qgs_points_to_tuples(points: List[QgsPointXY]) -> List[Point2D]:
    """Konwertuje listę QgsPointXY na listę krotek (x, y)."""
    return [(p.x(), p.y()) for p in points]


def tuples_to_qgs_points(tuples_list: List[Point2D]) -> List[QgsPointXY]:
    """Konwertuje listę krotek (x, y) na listę QgsPointXY."""
    return [QgsPointXY(x, y) for x, y in tuples_list]


class LayerModifier:
    """
    Klasa pomocnicza do bezpiecznej modyfikacji geometrii w edytowalnej warstwie QGIS.
    """

    @staticmethod
    def apply_segment_replacement(
        layer: QgsVectorLayer,
        feature_id: int,
        part_idx: int,
        ring_idx: int,
        seg_idx: int,
        replacement_pts: List[Point2D],
        command_name: str = "Wygnij odcinek w łuk"
    ) -> bool:
        """
        Podmienia odcinek w obiekcie o danym ID i zapisuje zmianę w historii cofania (Undo stack).
        """
        if not layer.isEditable():
            return False

        feature = layer.getFeature(feature_id)
        if not feature.isValid():
            return False

        orig_geom = feature.geometry()
        if orig_geom.isEmpty():
            return False

        new_geom = LayerModifier._replace_segment_in_geom(
            orig_geom, part_idx, ring_idx, seg_idx, replacement_pts
        )

        if new_geom is None or new_geom.isEmpty():
            return False

        if QgsWkbTypes.isMultiType(layer.wkbType()) and not new_geom.isMultipart():
            new_geom.convertToMultiType()

        layer.beginEditCommand(command_name)
        success = layer.changeGeometry(feature_id, new_geom)
        if success:
            layer.endEditCommand()
            layer.triggerRepaint()
            return True
        else:
            layer.destroyEditCommand()
            return False

    @staticmethod
    def apply_vertex_replacement(
        layer: QgsVectorLayer,
        feature_id: int,
        part_idx: int,
        ring_idx: int,
        vertex_idx: int,
        fillet_pts: List[Point2D],
        command_name: str = "Zaokrąglij wierzchołek"
    ) -> bool:
        """
        Podmienia pojedynczy wierzchołek w obiekcie.
        """
        return LayerModifier.apply_vertex_range_replacement(
            layer=layer,
            feature_id=feature_id,
            part_idx=part_idx,
            ring_idx=ring_idx,
            consumed_indices=[vertex_idx],
            replacement_pts=fillet_pts,
            command_name=command_name
        )

    @staticmethod
    def apply_vertex_range_replacement(
        layer: QgsVectorLayer,
        feature_id: int,
        part_idx: int,
        ring_idx: int,
        consumed_indices: List[int],
        replacement_pts: List[Point2D],
        command_name: str = "MSA: Zaokrąglij łukiem"
    ) -> bool:
        """
        Zastępuje zakres połykanych wierzchołków nową serią punktów łuku.
        """
        if not layer.isEditable():
            return False

        feature = layer.getFeature(feature_id)
        if not feature.isValid():
            return False

        orig_geom = feature.geometry()
        if orig_geom.isEmpty():
            return False

        new_geom = LayerModifier._replace_vertex_range_in_geom(
            orig_geom, part_idx, ring_idx, consumed_indices, replacement_pts
        )

        if new_geom is None or new_geom.isEmpty():
            return False

        if QgsWkbTypes.isMultiType(layer.wkbType()) and not new_geom.isMultipart():
            new_geom.convertToMultiType()

        layer.beginEditCommand(command_name)
        success = layer.changeGeometry(feature_id, new_geom)
        if success:
            layer.endEditCommand()
            layer.triggerRepaint()
            return True
        else:
            layer.destroyEditCommand()
            return False

    @staticmethod
    def _replace_segment_in_geom(
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        seg_idx: int,
        replacement_pts: List[Point2D]
    ) -> Optional[QgsGeometry]:
        """Zwraca nową QgsGeometry z podmienionym odcinkiem."""
        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.LineGeometry:
            if is_multi:
                multi_lines = geom.asMultiPolyline()
                if part_idx < 0 or part_idx >= len(multi_lines):
                    return None
                pts = qgs_points_to_tuples(multi_lines[part_idx])
                new_pts = replace_segment_in_points(pts, seg_idx, replacement_pts, is_closed=False)
                multi_lines[part_idx] = tuples_to_qgs_points(new_pts)
                return QgsGeometry.fromMultiPolylineXY(multi_lines)
            else:
                pts = qgs_points_to_tuples(geom.asPolyline())
                new_pts = replace_segment_in_points(pts, seg_idx, replacement_pts, is_closed=False)
                return QgsGeometry.fromPolylineXY(tuples_to_qgs_points(new_pts))

        elif geom_type == QgsWkbTypes.PolygonGeometry:
            if is_multi:
                multi_poly = geom.asMultiPolygon()
                if part_idx < 0 or part_idx >= len(multi_poly):
                    return None
                poly = multi_poly[part_idx]
                if ring_idx < 0 or ring_idx >= len(poly):
                    return None
                ring_pts = qgs_points_to_tuples(poly[ring_idx])
                new_ring_pts = replace_segment_in_points(ring_pts, seg_idx, replacement_pts, is_closed=True)
                poly[ring_idx] = tuples_to_qgs_points(new_ring_pts)
                multi_poly[part_idx] = poly
                return QgsGeometry.fromMultiPolygonXY(multi_poly)
            else:
                poly = geom.asPolygon()
                if ring_idx < 0 or ring_idx >= len(poly):
                    return None
                ring_pts = qgs_points_to_tuples(poly[ring_idx])
                new_ring_pts = replace_segment_in_points(ring_pts, seg_idx, replacement_pts, is_closed=True)
                poly[ring_idx] = tuples_to_qgs_points(new_ring_pts)
                return QgsGeometry.fromPolygonXY(poly)

        return None

    @staticmethod
    def _replace_vertex_range_in_geom(
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        consumed_indices: List[int],
        fillet_pts: List[Point2D]
    ) -> Optional[QgsGeometry]:
        """Zwraca nową QgsGeometry z podmienionym zakresem wierzchołków."""
        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.LineGeometry:
            if is_multi:
                multi_lines = geom.asMultiPolyline()
                if part_idx < 0 or part_idx >= len(multi_lines):
                    return None
                pts = qgs_points_to_tuples(multi_lines[part_idx])
                new_pts = replace_vertex_range_in_points(pts, consumed_indices, fillet_pts, is_closed=False)
                multi_lines[part_idx] = tuples_to_qgs_points(new_pts)
                return QgsGeometry.fromMultiPolylineXY(multi_lines)
            else:
                pts = qgs_points_to_tuples(geom.asPolyline())
                new_pts = replace_vertex_range_in_points(pts, consumed_indices, fillet_pts, is_closed=False)
                return QgsGeometry.fromPolylineXY(tuples_to_qgs_points(new_pts))

        elif geom_type == QgsWkbTypes.PolygonGeometry:
            if is_multi:
                multi_poly = geom.asMultiPolygon()
                if part_idx < 0 or part_idx >= len(multi_poly):
                    return None
                poly = multi_poly[part_idx]
                if ring_idx < 0 or ring_idx >= len(poly):
                    return None
                ring_pts = qgs_points_to_tuples(poly[ring_idx])
                new_ring_pts = replace_vertex_range_in_points(ring_pts, consumed_indices, fillet_pts, is_closed=True)
                poly[ring_idx] = tuples_to_qgs_points(new_ring_pts)
                multi_poly[part_idx] = poly
                return QgsGeometry.fromMultiPolygonXY(multi_poly)
            else:
                poly = geom.asPolygon()
                if ring_idx < 0 or ring_idx >= len(poly):
                    return None
                ring_pts = qgs_points_to_tuples(poly[ring_idx])
                new_ring_pts = replace_vertex_range_in_points(ring_pts, consumed_indices, fillet_pts, is_closed=True)
                poly[ring_idx] = tuples_to_qgs_points(new_ring_pts)
                return QgsGeometry.fromPolygonXY(poly)

        return None

    @staticmethod
    def add_feature(
        layer: QgsVectorLayer,
        geom: QgsGeometry,
        command_name: str = "MSA: Utwórz offset"
    ) -> Optional[int]:
        """
        Tworzy nowy obiekt z podaną geometrią w edytowalnej warstwie QGIS,
        uwzględniając transakcje i historię operacji (Undo/Redo).
        """
        if not layer or not layer.isEditable():
            return None
        if geom is None or geom.isEmpty():
            return None

        layer_geom_type = layer.geometryType()
        new_geom = QgsGeometry(geom)

        # Dopasowanie poligon -> linia (np. gdy odsuwamy granicę poligonu do warstwy liniowej)
        if layer_geom_type == QgsWkbTypes.LineGeometry and new_geom.type() == QgsWkbTypes.PolygonGeometry:
            if new_geom.isMultipart():
                lines = []
                for poly in new_geom.asMultiPolygon():
                    for ring in poly:
                        lines.append(ring)
                new_geom = QgsGeometry.fromMultiPolylineXY(lines)
            else:
                rings = new_geom.asPolygon()
                if rings:
                    new_geom = QgsGeometry.fromPolylineXY(rings[0])

        # Dopasowanie linia zamknięta -> poligon
        elif layer_geom_type == QgsWkbTypes.PolygonGeometry and new_geom.type() == QgsWkbTypes.LineGeometry:
            if not new_geom.isMultipart():
                polyline = new_geom.asPolyline()
                if polyline and len(polyline) >= 3:
                    if polyline[0] != polyline[-1]:
                        polyline.append(polyline[0])
                    new_geom = QgsGeometry.fromPolygonXY([polyline])

        # Dopasowanie typu Multi vs Single
        if QgsWkbTypes.isMultiType(layer.wkbType()) and not new_geom.isMultipart():
            new_geom.convertToMultiType()

        feat = QgsFeature(layer.fields())
        feat.setGeometry(new_geom)

        layer.beginEditCommand(command_name)
        success = layer.addFeature(feat)
        if success:
            layer.endEditCommand()
            layer.triggerRepaint()
            return feat.id()
        else:
            layer.destroyEditCommand()
            return None
