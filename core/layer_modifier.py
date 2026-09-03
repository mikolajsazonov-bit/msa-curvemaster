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
    QgsLineString,
    QgsMultiLineString,
    QgsPolygon,
    QgsMultiPolygon,
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

        adapted = LayerModifier.adapt_geometry_to_layer(layer, new_geom)
        if not adapted:
            return False
        final_geom = adapted[0]

        layer.beginEditCommand(command_name)
        success = layer.changeGeometry(feature_id, final_geom)
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

        adapted = LayerModifier.adapt_geometry_to_layer(layer, new_geom)
        if not adapted:
            return False
        final_geom = adapted[0]

        layer.beginEditCommand(command_name)
        success = layer.changeGeometry(feature_id, final_geom)
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
    def adapt_geometry_to_layer(layer: QgsVectorLayer, geom: QgsGeometry) -> List[QgsGeometry]:
        """
        Dopasowuje geometrię wejściową do dokładnego typu WKB i wymiarowości docelowej warstwy.
        Obsługuje:
        - Dopasowanie kategorii bazowej (Polygon -> Line, Line -> Polygon, GeometryCollection -> części)
        - Linearyzację łuków (gdy warstwa nie wspiera krzywych)
        - Wymiary Z i M (usuwanie Z/M gdy warstwa 2D, dodawanie Z/M=0 gdy warstwa 3D/M)
        - Wieloczęściowość (Multi vs Single):
          * dla warstw SinglePart dzieli MultiPart na pojedyncze geometrie
          * dla warstw MultiPart scala lub konwertuje do typu Multi
        Zwraca listę geometrii w 100% zgodnych z definicją warstwy, gwarantując
        poprawny zapis zmian bez błędów "typ geometrii nie jest zgodny z bieżącą warstwą".
        """
        if geom is None or geom.isEmpty() or not layer:
            return []

        layer_geom_type = layer.geometryType()
        layer_wkb = layer.wkbType()
        layer_is_multi = QgsWkbTypes.isMultiType(layer_wkb)
        layer_has_z = QgsWkbTypes.hasZ(layer_wkb)
        layer_has_m = QgsWkbTypes.hasM(layer_wkb)
        layer_is_curved = QgsWkbTypes.isCurvedType(layer_wkb)

        geoms: List[QgsGeometry] = []

        # 1. Konwersja kategorii bazowej
        if layer_geom_type == QgsWkbTypes.LineGeometry:
            if geom.type() == QgsWkbTypes.PolygonGeometry:
                # Wyciągnięcie wszystkich pierścieni jako linii z zachowaniem współrzędnych Z/M
                for part in geom.parts():
                    if hasattr(part, 'exteriorRing') and part.exteriorRing():
                        geoms.append(QgsGeometry(part.exteriorRing().clone()))
                    if hasattr(part, 'numInteriorRings'):
                        for i in range(part.numInteriorRings()):
                            geoms.append(QgsGeometry(part.interiorRing(i).clone()))
                if not geoms:
                    if geom.isMultipart():
                        for poly in geom.asMultiPolygon():
                            for ring in poly:
                                geoms.append(QgsGeometry.fromPolylineXY(ring))
                    else:
                        for ring in geom.asPolygon():
                            geoms.append(QgsGeometry.fromPolylineXY(ring))
            elif geom.type() == QgsWkbTypes.LineGeometry:
                geoms.append(QgsGeometry(geom))
            elif geom.wkbType() in (
                QgsWkbTypes.GeometryCollection,
                QgsWkbTypes.GeometryCollectionZ,
                QgsWkbTypes.GeometryCollectionM,
                QgsWkbTypes.GeometryCollectionZM
            ):
                for part in geom.parts():
                    if part.geometryType() == QgsWkbTypes.LineGeometry:
                        geoms.append(QgsGeometry(part.clone()))
                    elif part.geometryType() == QgsWkbTypes.PolygonGeometry:
                        if hasattr(part, 'exteriorRing') and part.exteriorRing():
                            geoms.append(QgsGeometry(part.exteriorRing().clone()))
                        if hasattr(part, 'numInteriorRings'):
                            for i in range(part.numInteriorRings()):
                                geoms.append(QgsGeometry(part.interiorRing(i).clone()))

        elif layer_geom_type == QgsWkbTypes.PolygonGeometry:
            if geom.type() == QgsWkbTypes.LineGeometry:
                # Zamknięcie polilinii i konwersja na poligon
                if geom.isMultipart():
                    for polyline in geom.asMultiPolyline():
                        if len(polyline) >= 3:
                            ring = list(polyline)
                            if ring[0] != ring[-1]:
                                ring.append(ring[0])
                            geoms.append(QgsGeometry.fromPolygonXY([ring]))
                else:
                    polyline = geom.asPolyline()
                    if len(polyline) >= 3:
                        ring = list(polyline)
                        if ring[0] != ring[-1]:
                            ring.append(ring[0])
                        geoms.append(QgsGeometry.fromPolygonXY([ring]))
            elif geom.type() == QgsWkbTypes.PolygonGeometry:
                geoms.append(QgsGeometry(geom))

        else:
            geoms.append(QgsGeometry(geom))

        if not geoms:
            return []

        processed: List[QgsGeometry] = []
        for g in geoms:
            if g is None or g.isEmpty():
                continue

            # 2. Linearyzacja krzywych jeśli warstwa nie obsługuje krzywych
            if not layer_is_curved and QgsWkbTypes.isCurvedType(g.wkbType()):
                g = QgsGeometry(g.constGet().segmentize())

            # 3. Dopasowanie wymiaru Z
            geom_has_z = QgsWkbTypes.hasZ(g.wkbType())
            if not layer_has_z and geom_has_z:
                g.get().dropZValue()
            elif layer_has_z and not geom_has_z:
                g.get().addZValue(0.0)

            # 4. Dopasowanie wymiaru M
            geom_has_m = QgsWkbTypes.hasM(g.wkbType())
            if not layer_has_m and geom_has_m:
                g.get().dropMValue()
            elif layer_has_m and not geom_has_m:
                g.get().addMValue(0.0)

            processed.append(g)

        if not processed:
            return []

        # 5. Dopasowanie typu Multi vs Single
        result: List[QgsGeometry] = []
        if layer_is_multi:
            if len(processed) == 1:
                g = processed[0]
                if not g.isMultipart():
                    g.convertToMultiType()
                result.append(g)
            else:
                # Połączenie wielu części w jedną geometrię MultiPart
                if layer_geom_type == QgsWkbTypes.LineGeometry:
                    mls = QgsMultiLineString()
                    for g in processed:
                        for part in g.parts():
                            mls.addGeometry(part.clone())
                    res = QgsGeometry(mls)
                elif layer_geom_type == QgsWkbTypes.PolygonGeometry:
                    mp = QgsMultiPolygon()
                    for g in processed:
                        for part in g.parts():
                            mp.addGeometry(part.clone())
                    res = QgsGeometry(mp)
                else:
                    res = processed[0]
                    res.convertToMultiType()

                if not layer_has_z and QgsWkbTypes.hasZ(res.wkbType()):
                    res.get().dropZValue()
                elif layer_has_z and not QgsWkbTypes.hasZ(res.wkbType()):
                    res.get().addZValue(0.0)
                if not layer_has_m and QgsWkbTypes.hasM(res.wkbType()):
                    res.get().dropMValue()
                elif layer_has_m and not QgsWkbTypes.hasM(res.wkbType()):
                    res.get().addMValue(0.0)
                result.append(res)
        else:
            # Warstwa jednoczęściowa (SinglePart): rozbicie MultiPart na pojedyncze geometrie
            for g in processed:
                if g.isMultipart():
                    for part in g.parts():
                        single_g = QgsGeometry(part.clone())
                        if not layer_has_z and QgsWkbTypes.hasZ(single_g.wkbType()):
                            single_g.get().dropZValue()
                        elif layer_has_z and not QgsWkbTypes.hasZ(single_g.wkbType()):
                            single_g.get().addZValue(0.0)
                        if not layer_has_m and QgsWkbTypes.hasM(single_g.wkbType()):
                            single_g.get().dropMValue()
                        elif layer_has_m and not QgsWkbTypes.hasM(single_g.wkbType()):
                            single_g.get().addMValue(0.0)
                        result.append(single_g)
                else:
                    result.append(g)

        return result

    @staticmethod
    def add_feature(
        layer: QgsVectorLayer,
        geom: QgsGeometry,
        command_name: str = "MSA: Utwórz offset"
    ) -> Optional[int]:
        """
        Tworzy nowy obiekt (lub obiekty w przypadku rozbicia multipart na singlepart)
        z podaną geometrią w edytowalnej warstwie QGIS, gwarantując pełną zgodność
        typu WKB oraz wymiarowości Z/M z definicją warstwy, z obsługą Undo/Redo.
        """
        if not layer or not layer.isEditable():
            return None
        if geom is None or geom.isEmpty():
            return None

        adapted_geoms = LayerModifier.adapt_geometry_to_layer(layer, geom)
        if not adapted_geoms:
            return None

        layer.beginEditCommand(command_name)
        added_ids = []
        for g in adapted_geoms:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(g)
            if layer.addFeature(feat):
                added_ids.append(feat.id())

        if added_ids:
            layer.endEditCommand()
            layer.triggerRepaint()
            return added_ids[0]
        else:
            layer.destroyEditCommand()
            return None
