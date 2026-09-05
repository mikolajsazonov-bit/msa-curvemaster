#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
***************************************************************************
*   MSA: CurveMaster - Narzędzia geometrii dla Smart Pour (wylewanie)     *
*   Autor: Mikołaj Sazonov                                                *
***************************************************************************
"""

from typing import List, Optional, Tuple, Set, Dict, Any
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsFeatureRequest,
    QgsMessageLog,
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsSymbol
)
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QColor, QPixmap, QPainter, QBrush, QPen, QIcon
from .layer_modifier import LayerModifier
from .offset_utils import extract_rings_as_line


# Standardowe nazwy kolumn kategorii w projektach CAD/GIS
CATEGORY_FIELD_CANDIDATES = (
    'kategoria',
    'category',
    'typ',
    'type',
    'nawierzchnia',
    'surface',
    'material',
    'rodzaj'
)


def find_category_field_name(layer: Optional[QgsVectorLayer]) -> Optional[str]:
    """
    Wyszukuje najbardziej prawdopodobną nazwę kolumny dla kategorii nawierzchni.
    Najpierw sprawdza atrybut klasyfikacji ze stylizacji warstwy (jeśli warstwa jest skategoryzowana).
    Następnie sprawdza standardowe nazwy kandydatów, a na końcu pierwsze pole tekstowe.
    """
    if not layer or not layer.isValid():
        return None

    # 1. Sprawdzenie atrybutu kategoryzacji w rendererze warstwy
    try:
        renderer = layer.renderer()
        if isinstance(renderer, QgsCategorizedSymbolRenderer):
            class_attr = renderer.classAttribute()
            if class_attr and layer.fields().indexOf(class_attr) >= 0:
                return class_attr
    except Exception as err:
        QgsMessageLog.logMessage(f"Odczyt atrybutu z renderera: {err}", "CurveMaster", Qgis.Info)

    fields = layer.fields()
    field_names = [f.name() for f in fields]
    field_names_lower = [name.lower() for name in field_names]

    # 2. Sprawdzenie znanych nazw kandydatów
    for candidate in CATEGORY_FIELD_CANDIDATES:
        if candidate in field_names_lower:
            idx = field_names_lower.index(candidate)
            return field_names[idx]

    # 3. Fallback: pierwsze pole tekstowe
    for field in fields:
        if field.typeName().lower() in ('string', 'text', 'varchar', 'character'):
            # Pomijamy ID/klucze
            if field.name().lower() not in ('id', 'uuid', 'guid', 'fid', 'ogc_fid'):
                return field.name()

    return None


def get_contrast_text_color(bg_color: QColor) -> QColor:
    """
    Wyznacza kontrastowy kolor tekstu (czysta biel lub ciemny grafit)
    na podstawie luminancji zadanego koloru tła (formuła W3C).
    """
    luminance = 0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()
    if luminance > 160:
        return QColor(33, 37, 41)  # Ciemny grafit dla jasnego tła
    return QColor(255, 255, 255)  # Biel dla ciemnego tła


class CategoryStyleInfo:
    """
    Przechowuje informacje o stylu wizualnym danej kategorii nawierzchni.
    Pobierane ze stylizacji aktywnej warstwy w QGIS.
    Generuje bezpieczne, czyste próbki barwne (swatches) za pomocą QPainter,
    eliminując ryzyko awarii pamięci (SIGSEGV) w silniku renderującym SIP/C++.
    """
    def __init__(
        self,
        name: str,
        fill_color: QColor,
        stroke_color: Optional[QColor] = None,
        text_color: Optional[QColor] = None,
        symbol: Optional[Any] = None
    ):
        self.name = name
        self.fill_color = fill_color if (fill_color and fill_color.isValid()) else QColor("#2b2d42")
        self.stroke_color = stroke_color if (stroke_color and stroke_color.isValid()) else self.fill_color.darker(130)
        self.text_color = text_color if text_color else get_contrast_text_color(self.fill_color)
        self._icons: Dict[int, QIcon] = {}
        self._pixmaps: Dict[int, QPixmap] = {}

    def get_icon(self, size: int = 16) -> Optional[QIcon]:
        """Zwraca QIcon z próbką stylu (swatch)."""
        if size in self._icons:
            return self._icons[size]

        try:
            pixmap = self.get_pixmap(size)
            if pixmap and not pixmap.isNull():
                icon = QIcon(pixmap)
                self._icons[size] = icon
                return icon
        except Exception as err:
            QgsMessageLog.logMessage(f"Generowanie ikony swatch: {err}", "CurveMaster", Qgis.Info)
        return None

    def get_pixmap(self, size: int = 16) -> Optional[QPixmap]:
        """Zwraca QPixmap z próbką stylu dla etykiet i podglądów."""
        if size in self._pixmaps:
            return self._pixmaps[size]

        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(self.fill_color))
            painter.setPen(QPen(self.stroke_color, 1.5))
            painter.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
            painter.end()
            self._pixmaps[size] = pixmap
            return pixmap
        except Exception as err:
            QgsMessageLog.logMessage(f"Generowanie pixmapy swatch: {err}", "CurveMaster", Qgis.Info)
            return None


def get_layer_category_styles(
    layer: Optional[QgsVectorLayer],
    field_name: Optional[str] = None
) -> Dict[str, CategoryStyleInfo]:
    """
    Odczytuje stylizację z aktywnej warstwy dla zdefiniowanych w niej kategorii.
    Zwraca słownik: nazwa_kategorii -> CategoryStyleInfo.
    Bez zgadywania - pobiera wyłącznie to, co jest faktycznie zdefiniowane w stylizacji warstwy.
    """
    styles: Dict[str, CategoryStyleInfo] = {}
    if not layer or not layer.isValid():
        return styles

    renderer = layer.renderer()
    if not renderer:
        return styles

    # Przypadek 1: Symbolika zróżnicowana (Categorized)
    if isinstance(renderer, QgsCategorizedSymbolRenderer):
        for cat in renderer.categories():
            try:
                val = str(cat.value()).strip() if cat.value() is not None else ""
                label = cat.label().strip() if cat.label() else ""
                sym = cat.symbol()
                if not sym:
                    continue

                fill_color = sym.color()
                if not fill_color or not fill_color.isValid():
                    continue

                stroke_color = None
                if sym.symbolLayerCount() > 0:
                    sl = sym.symbolLayer(0)
                    if hasattr(sl, 'strokeColor'):
                        sc = sl.strokeColor()
                        if sc and sc.isValid() and sc.alpha() > 0:
                            stroke_color = sc
                if not stroke_color:
                    stroke_color = fill_color.darker(130)

                style_info = CategoryStyleInfo(
                    name=val or label,
                    fill_color=fill_color,
                    stroke_color=stroke_color
                )

                if val:
                    styles[val] = style_info
                    styles[val.lower()] = style_info
                if label:
                    styles[label] = style_info
                    styles[label.lower()] = style_info
            except Exception as err:
                QgsMessageLog.logMessage(f"Odczyt stylu kategorii: {err}", "CurveMaster", Qgis.Info)

    # Przypadek 2: Symbolika oparta na regułach (Rule-Based)
    elif isinstance(renderer, QgsRuleBasedRenderer):
        root = renderer.rootRule()
        if root:
            for rule in root.children():
                try:
                    sym = rule.symbol()
                    if not sym:
                        continue

                    label = rule.label().strip() if rule.label() else ""
                    expr = rule.filterExpression().strip() if rule.filterExpression() else ""

                    fill_color = sym.color()
                    if not fill_color or not fill_color.isValid():
                        continue

                    stroke_color = None
                    if sym.symbolLayerCount() > 0:
                        sl = sym.symbolLayer(0)
                        if hasattr(sl, 'strokeColor'):
                            sc = sl.strokeColor()
                            if sc and sc.isValid() and sc.alpha() > 0:
                                stroke_color = sc
                    if not stroke_color:
                        stroke_color = fill_color.darker(130)

                    style_info = CategoryStyleInfo(
                        name=label or expr,
                        fill_color=fill_color,
                        stroke_color=stroke_color
                    )

                    if label:
                        styles[label] = style_info
                        styles[label.lower()] = style_info

                    if expr:
                        import re
                        m = re.search(r"=\s*'([^']+)'", expr)
                        if m:
                            extracted_val = m.group(1).strip()
                            styles[extracted_val] = style_info
                            styles[extracted_val.lower()] = style_info
                except Exception as err:
                    QgsMessageLog.logMessage(f"Odczyt stylu reguły: {err}", "CurveMaster", Qgis.Info)

    # Przypadek 3: Pojedynczy symbol (Single Symbol)
    elif isinstance(renderer, QgsSingleSymbolRenderer):
        try:
            sym = renderer.symbol()
            if sym:
                fill_color = sym.color()
                if fill_color and fill_color.isValid():
                    stroke_color = None
                    if sym.symbolLayerCount() > 0:
                        sl = sym.symbolLayer(0)
                        if hasattr(sl, 'strokeColor'):
                            sc = sl.strokeColor()
                            if sc and sc.isValid() and sc.alpha() > 0:
                                stroke_color = sc
                    if not stroke_color:
                        stroke_color = fill_color.darker(130)

                    style_info = CategoryStyleInfo(
                        name=layer.name(),
                        fill_color=fill_color,
                        stroke_color=stroke_color
                    )
                    styles['__single__'] = style_info
        except Exception as err:
            QgsMessageLog.logMessage(f"Odczyt stylu pojedynczego: {err}", "CurveMaster", Qgis.Info)

    return styles


def find_category_style(
    styles: Dict[str, CategoryStyleInfo],
    category_name: str
) -> Optional[CategoryStyleInfo]:
    """
    Wyszukuje styl dla zadanej nazwy kategorii w słowniku stylów warstwy.
    Bez zgadywania - zwraca styl jeśli istnieje w warstwie, w przeciwnym razie None.
    """
    if not category_name or not styles:
        return None

    clean = category_name.strip()
    if clean in styles:
        return styles[clean]
    if clean.lower() in styles:
        return styles[clean.lower()]

    if '__single__' in styles:
        return styles['__single__']

    return None


def get_layer_unique_categories(layer: Optional[QgsVectorLayer], field_name: Optional[str] = None) -> List[str]:
    """
    Zwraca posortowaną alfabetycznie listę unikalnych wartości tekstowych
    z kolumny kategorii w aktywnej warstwie.
    Uwzględnia zarówno obiekty już istniejące w warstwie, jak i kategorie
    zdefiniowane w stylizacji warstwy (np. na nowej/pustej warstwie).
    """
    if not layer or not layer.isValid():
        return []

    if not field_name:
        field_name = find_category_field_name(layer)
        if not field_name:
            return []

    categories: Set[str] = set()

    # 1. Odczyt z istniejących obiektów
    field_idx = layer.fields().indexOf(field_name)
    if field_idx >= 0:
        try:
            unique_vals = layer.uniqueValues(field_idx)
            for val in unique_vals:
                if val is not None:
                    s_val = str(val).strip()
                    if s_val and s_val.lower() != 'null':
                        categories.add(s_val)
        except Exception as err:
            QgsMessageLog.logMessage(f"Błąd odczytu unikalnych kategorii: {err}", "CurveMaster", Qgis.Warning)

    # 2. Odczyt z definicji kategoryzacji w rendererze (jeśli obecna)
    try:
        renderer = layer.renderer()
        if isinstance(renderer, QgsCategorizedSymbolRenderer):
            for cat in renderer.categories():
                v = cat.value()
                if v is not None:
                    sv = str(v).strip()
                    if sv and sv.lower() != 'null':
                        categories.add(sv)
        elif isinstance(renderer, QgsRuleBasedRenderer):
            root = renderer.rootRule()
            if root:
                for rule in root.children():
                    lbl = rule.label().strip()
                    if lbl and not lbl.startswith('['):
                        categories.add(lbl)
    except Exception as err:
        QgsMessageLog.logMessage(f"Błąd odczytu kategorii z renderera: {err}", "CurveMaster", Qgis.Info)

    # Sortowanie alfabetyczne (niewrażliwe na wielkość liter)
    return sorted(list(categories), key=lambda x: x.lower())


def compute_pour_polygon(
    click_pt: QgsPointXY,
    radius: float,
    boundary_geometries: List[QgsGeometry],
    tolerance: float = 0.05
) -> Optional[QgsGeometry]:
    """
    Wyznacza poligon obwiedni wokół punktu kliknięcia click_pt,
    ograniczony przez zbiór linii boundary_geometries oraz kołowy bufor odcięcia o promieniu radius.
    """
    if radius <= 0.05 or not click_pt:
        return None

    # 1. Kołowy bufor odcięcia wokół punktu kliknięcia (36 segmentów na ćwiartkę = 144 segmenty okręgu)
    pt_geom = QgsGeometry.fromPointXY(click_pt)
    disk = pt_geom.buffer(radius, 36)
    if not disk or disk.isEmpty():
        return None

    disk_boundary = extract_rings_as_line(disk)
    if not disk_boundary or disk_boundary.isEmpty():
        return None

    # 2. Zbieranie linii ograniczających w zasięgu bufora
    lines_to_node: List[QgsGeometry] = [disk_boundary]
    # Używamy prostokąta lekko powiększonego (o 5%), aby linie przecinały krawędź dysku
    clip_rect = disk.boundingBox().buffered(max(2.0, radius * 0.1))
    clip_box_geom = QgsGeometry.fromRect(clip_rect)

    for geom in boundary_geometries:
        if not geom or geom.isEmpty():
            continue

        if not geom.boundingBox().intersects(clip_rect):
            continue

        # Jeśli geometria jest poligonem, pobieramy jej obrys
        if geom.type() == QgsWkbTypes.PolygonGeometry:
            line_part = extract_rings_as_line(geom)
        elif geom.type() == QgsWkbTypes.LineGeometry:
            line_part = geom
        else:
            continue

        if not line_part or line_part.isEmpty():
            continue

        # Docinamy linię do powiększonego prostokąta, aby nie przetwarzać długich linii poza zakresem
        try:
            inter = line_part.intersection(clip_box_geom)
            if inter and not inter.isEmpty():
                lines_to_node.append(inter)
        except Exception as err:
            QgsMessageLog.logMessage(f"Błąd przycinania linii do clip_box: {err}", "CurveMaster", Qgis.Info)
            lines_to_node.append(line_part)

    # 3. Nodowanie linii (przecięcie w węzłach za pomocą unaryUnion)
    try:
        combined_lines = QgsGeometry.unaryUnion(lines_to_node)
    except Exception as err:
        QgsMessageLog.logMessage(f"Błąd unaryUnion linii obwiedni: {err}", "CurveMaster", Qgis.Warning)
        return None

    if not combined_lines or combined_lines.isEmpty():
        return None

    # 4. Poligonizacja siatki linii
    try:
        # QgsGeometry.polygonize zwraca geometrię złożoną (GeometryCollection)
        polys_geom = QgsGeometry.polygonize([combined_lines])
    except Exception as err:
        QgsMessageLog.logMessage(f"Błąd QgsGeometry.polygonize: {err}", "CurveMaster", Qgis.Warning)
        return None

    if not polys_geom or polys_geom.isEmpty():
        return None

    # 5. Wyszukanie komórki/poligonu zawierającego punkt kliknięcia click_pt
    target_poly: Optional[QgsGeometry] = None
    min_dist = float('inf')

    # asGeometryCollection() zwraca listę pojedynczych geometrii QgsGeometry
    poly_list = polys_geom.asGeometryCollection() if polys_geom.isMultipart() else [polys_geom]

    for poly in poly_list:
        if not poly or poly.isEmpty():
            continue

        # Sprawdzenie czy punkt jest wewnątrz poligonu
        if poly.contains(pt_geom):
            target_poly = poly
            break

        # Fallback dla kliknięć bardzo blisko krawędzi
        d = poly.distance(pt_geom)
        if d < min_dist and d < tolerance:
            min_dist = d
            target_poly = poly

    if not target_poly:
        return None

    # Oczyszczenie geometrii
    cleaned = target_poly.makeValid()
    if not cleaned or cleaned.isEmpty():
        return target_poly

    return cleaned


def merge_polygon_with_category(
    layer: QgsVectorLayer,
    new_geom: QgsGeometry,
    category_field: Optional[str],
    category_value: str,
    command_name: str = "MSA: Zalej nawierzchnię"
) -> bool:
    """
    Wstawia poligon do warstwy lub zrasta go (Auto-Merge / union) z istniejącymi
    obiektami tej samej kategorii, jeśli się z nimi styka.
    Wszystko w ramach jednej transakcji Undo/Redo.
    """
    if not layer or not layer.isEditable() or not new_geom or new_geom.isEmpty():
        return False

    field_idx = layer.fields().indexOf(category_field) if category_field else -1

    # 1. Wyszukanie obiektów w tej samej warstwie, które stykają się z new_geom
    search_rect = new_geom.boundingBox()
    request = QgsFeatureRequest().setFilterRect(search_rect)

    matching_features: List[QgsFeature] = []
    category_str = str(category_value).strip().lower() if category_value else ""

    for feat in layer.getFeatures(request):
        feat_geom = feat.geometry()
        if not feat_geom or feat_geom.isEmpty():
            continue

        # Sprawdzamy czy obiekty się stykają lub przecinają
        if not feat_geom.intersects(new_geom):
            continue

        # Sprawdzamy zgodność kategorii
        if field_idx >= 0:
            feat_val = str(feat.attribute(field_idx)).strip().lower() if feat.attribute(field_idx) is not None else ""
            if feat_val != category_str:
                continue
        elif category_str:
            # Jeśli brak pola kategorii, a podano wartość, traktujemy jako brak dopasowania
            continue

        matching_features.append(feat)

    # 2. Przypadek A: Znaleziono obiekty tej samej kategorii -> Auto-Merge (scalenie)
    if matching_features:
        layer.beginEditCommand(command_name)
        try:
            merged_geom = QgsGeometry(new_geom)
            for feat in matching_features:
                merged_geom = merged_geom.combine(feat.geometry())

            merged_geom = merged_geom.makeValid()

            # Dopasowanie typu WKB do warstwy
            adapted_list = LayerModifier.adapt_geometry_to_layer(layer, merged_geom)
            if not adapted_list:
                layer.destroyEditCommand()
                return False

            final_geom = adapted_list[0]

            # Aktualizujemy geometrię pierwszego pasującego obiektu
            primary_feat = matching_features[0]
            success = layer.changeGeometry(primary_feat.id(), final_geom)
            if not success:
                layer.destroyEditCommand()
                return False

            # Jeśli nowy poligon scalił kilka dotychczas osobnych fragmentów, usuwamy pozostałe
            if len(matching_features) > 1:
                ids_to_delete = [f.id() for f in matching_features[1:]]
                layer.deleteFeatures(ids_to_delete)

            layer.endEditCommand()
            layer.triggerRepaint()
            return True
        except Exception as err:
            QgsMessageLog.logMessage(f"Błąd scalania Auto-Merge: {err}", "CurveMaster", Qgis.Warning)
            layer.destroyEditCommand()
            return False

    # 3. Przypadek B: Brak obiektów do scalenia -> Utworzenie nowego obiektu
    adapted_list = LayerModifier.adapt_geometry_to_layer(layer, new_geom)
    if not adapted_list:
        return False

    layer.beginEditCommand(command_name)
    added = False
    for g in adapted_list:
        feat = QgsFeature(layer.fields())
        # Bezpieczne atrybuty - wyzerowanie fid
        attrs = [None] * len(layer.fields())
        if field_idx >= 0 and category_value:
            attrs[field_idx] = category_value
        feat.setAttributes(attrs)
        feat.setGeometry(g)
        if layer.addFeature(feat):
            added = True

    if added:
        layer.endEditCommand()
        layer.triggerRepaint()
        return True
    else:
        layer.destroyEditCommand()
        return False
