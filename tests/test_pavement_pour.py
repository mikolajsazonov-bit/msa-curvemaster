#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Testy jednostkowe dla narzędzia Smart Pour (Wylewanie nawierzchni).
"""

import unittest
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsFields,
    QgsWkbTypes,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsFillSymbol,
    QgsRectangle
)
from PyQt5.QtCore import QVariant
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication

if not QApplication.instance():
    _qapp = QApplication(['test', '-platform', 'offscreen'])

from core.pavement_pour_utils import (
    find_category_field_name,
    get_layer_unique_categories,
    compute_pour_polygon,
    merge_polygon_with_category,
    get_contrast_text_color,
    get_layer_category_styles,
    find_category_style,
    CategoryStyleInfo,
    find_polygon_feature_at_point,
    erase_polygon_with_radius
)


class TestPavementPourUtils(unittest.TestCase):

    def setUp(self):
        # Tworzymy warstwę poligonową w pamięci z polem 'kategoria'
        self.layer = QgsVectorLayer("Polygon?crs=EPSG:2180", "TestSurfaces", "memory")
        pr = self.layer.dataProvider()
        pr.addAttributes([
            QgsField("fid", QVariant.Int),
            QgsField("kategoria", QVariant.String)
        ])
        self.layer.updateFields()
        self.layer.startEditing()

    def tearDown(self):
        if self.layer.isEditable():
            self.layer.rollBack()

    def test_find_category_field_name_without_guessing(self):
        # 1. Warstwa bez stylizacji opartej na unikalnych wartościach -> None (bez zgadywania!)
        self.assertIsNone(find_category_field_name(self.layer))

        # 2. Warstwa ze stylizacją kategoryzowaną (QgsCategorizedSymbolRenderer)
        self.layer.setRenderer(QgsCategorizedSymbolRenderer("kategoria", []))
        self.assertEqual(find_category_field_name(self.layer), "kategoria")

        # 3. Warstwa z inną nazwą w stylizacji kategoryzowanej
        layer2 = QgsVectorLayer("Polygon?crs=EPSG:2180", "Test2", "memory")
        layer2.dataProvider().addAttributes([
            QgsField("id", QVariant.Int),
            QgsField("nawierzchnia", QVariant.String)
        ])
        layer2.updateFields()
        layer2.setRenderer(QgsCategorizedSymbolRenderer("nawierzchnia", []))
        self.assertEqual(find_category_field_name(layer2), "nawierzchnia")

    def test_get_layer_unique_categories_sorted(self):
        pr = self.layer.dataProvider()
        f1 = QgsFeature(self.layer.fields())
        f1.setAttributes([1, "trawa"])
        f2 = QgsFeature(self.layer.fields())
        f2.setAttributes([2, "asfalt"])
        f3 = QgsFeature(self.layer.fields())
        f3.setAttributes([3, "Chodnik"])
        f4 = QgsFeature(self.layer.fields())
        f4.setAttributes([4, "asfalt"])  # duplikat
        f5 = QgsFeature(self.layer.fields())
        f5.setAttributes([5, None])       # null
        pr.addFeatures([f1, f2, f3, f4, f5])
        self.layer.updateExtents()

        cats = get_layer_unique_categories(self.layer, "kategoria")
        # Oczekujemy posortowanych alfabetycznie unikalnych wartości
        self.assertEqual([c.lower() for c in cats], ["asfalt", "chodnik", "trawa"])

    def test_get_layer_unique_categories_empty_no_fallback(self):
        # Nowa pusta warstwa bez żadnych kategorii -> pusta lista (brak sztucznego fallbacku 'Asfalt')
        empty_layer = QgsVectorLayer("Polygon?crs=EPSG:2180", "Empty", "memory")
        empty_layer.dataProvider().addAttributes([QgsField("kategoria", QVariant.String)])
        empty_layer.updateFields()
        cats = get_layer_unique_categories(empty_layer, "kategoria")
        self.assertEqual(cats, [])

    def test_merge_polygon_without_category_field(self):
        geom = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]])
        success = merge_polygon_with_category(self.layer, geom, None, "")
        self.assertTrue(success)
        self.assertEqual(self.layer.featureCount(), 1)

    def test_compute_pour_polygon_enclosed(self):
        # Kwadrat 10x10 od (0,0) do (10,10)
        lines = [
            QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(10, 0)]),
            QgsGeometry.fromPolylineXY([QgsPointXY(10, 0), QgsPointXY(10, 10)]),
            QgsGeometry.fromPolylineXY([QgsPointXY(10, 10), QgsPointXY(0, 10)]),
            QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(0, 0)])
        ]
        click_pt = QgsPointXY(5, 5)
        # Promień 20m - większy niż kwadrat
        poly = compute_pour_polygon(click_pt, 20.0, lines)
        self.assertIsNotNone(poly)
        self.assertTrue(poly.isGeosValid())
        # Pole powinno wynosić dokładnie 100
        self.assertAlmostEqual(poly.area(), 100.0, places=2)

    def test_compute_pour_polygon_open_corridor(self):
        # Dwie równoległe linie y = 0 oraz y = 10 od x = -50 do x = +50
        lines = [
            QgsGeometry.fromPolylineXY([QgsPointXY(-50, 0), QgsPointXY(50, 0)]),
            QgsGeometry.fromPolylineXY([QgsPointXY(-50, 10), QgsPointXY(50, 10)])
        ]
        click_pt = QgsPointXY(0, 5)
        radius = 15.0
        poly = compute_pour_polygon(click_pt, radius, lines)
        self.assertIsNotNone(poly)
        self.assertTrue(poly.isGeosValid())
        self.assertTrue(poly.contains(QgsPointXY(0, 5)))
        # Powinien być ograniczony między y=0 a y=10
        bbox = poly.boundingBox()
        self.assertAlmostEqual(bbox.yMinimum(), 0.0, places=2)
        self.assertAlmostEqual(bbox.yMaximum(), 10.0, places=2)
        # Końce powinny być ograniczone przez promień (bbox x w okolicach [-15, 15])
        self.assertGreaterEqual(bbox.xMinimum(), -15.1)
        self.assertLessEqual(bbox.xMaximum(), 15.1)

    def test_auto_merge_same_category(self):
        # Wstawiamy pierwszy prostokąt asfaltu (0,0) do (10,10)
        geom1 = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]])
        success1 = merge_polygon_with_category(self.layer, geom1, "kategoria", "asfalt")
        self.assertTrue(success1)
        self.assertEqual(self.layer.featureCount(), 1)

        # Wstawiamy sąsiadujący prostokąt asfaltu (10,0) do (20,10)
        geom2 = QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]])
        success2 = merge_polygon_with_category(self.layer, geom2, "kategoria", "asfalt")
        self.assertTrue(success2)

        # Powinien nadal być 1 obiekt o podwójnej powierzchni (200 m2)
        self.assertEqual(self.layer.featureCount(), 1)
        feat = next(self.layer.getFeatures())
        self.assertAlmostEqual(feat.geometry().area(), 200.0, places=2)
        self.assertEqual(feat["kategoria"], "asfalt")

    def test_no_merge_different_category(self):
        # Wstawiamy asfalt (0,0) do (10,10)
        geom1 = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]])
        merge_polygon_with_category(self.layer, geom1, "kategoria", "asfalt")

        # Wstawiamy stykający się chodnik (10,0) do (20,10)
        geom2 = QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]])
        merge_polygon_with_category(self.layer, geom2, "kategoria", "chodnik")

        # Powinny być 2 osobne obiekty!
        self.assertEqual(self.layer.featureCount(), 2)
        feats = list(self.layer.getFeatures())
        categories = {f["kategoria"] for f in feats}
        self.assertEqual(categories, {"asfalt", "chodnik"})

    def test_contrast_text_color(self):
        # Ciemne tło (asfalt, ciemna zieleń, czerwień) -> biały tekst
        dark_color = QColor("#2b2d42")
        self.assertEqual(get_contrast_text_color(dark_color).name(), "#ffffff")

        black_color = QColor("#000000")
        self.assertEqual(get_contrast_text_color(black_color).name(), "#ffffff")

        # Jasne tło (żółty, biały, jasny beż) -> ciemny tekst (#212529)
        yellow_color = QColor("#ffc107")
        self.assertEqual(get_contrast_text_color(yellow_color).name(), "#212529")

        white_color = QColor("#ffffff")
        self.assertEqual(get_contrast_text_color(white_color).name(), "#212529")

    def test_layer_category_styles_categorized(self):
        # Tworzymy osobną warstwę ze stylizacją zróżnicowaną (Categorized)
        cat_layer = QgsVectorLayer("Polygon?crs=EPSG:2180", "StyledLayer", "memory")
        cat_layer.dataProvider().addAttributes([
            QgsField("kategoria", QVariant.String)
        ])
        cat_layer.updateFields()

        sym1 = QgsFillSymbol.createSimple({'color': '#333333', 'outline_color': '#111111'})
        sym2 = QgsFillSymbol.createSimple({'color': '#28a745', 'outline_color': '#1e7e34'})

        cats = [
            QgsRendererCategory('asfalt', sym1, 'Nawierzchnia asfaltowa'),
            QgsRendererCategory('trawa', sym2, 'Trawnik z rolki'),
        ]
        cat_layer.setRenderer(QgsCategorizedSymbolRenderer('kategoria', cats))

        styles = get_layer_category_styles(cat_layer)
        self.assertIn('asfalt', styles)
        self.assertIn('trawa', styles)
        self.assertEqual(styles['asfalt'].fill_color.name(), '#333333')
        self.assertEqual(styles['trawa'].fill_color.name(), '#28a745')
        self.assertEqual(styles['asfalt'].stroke_color.name(), '#111111')

        # Sprawdzenie find_category_style
        style_asf = find_category_style(styles, "Asfalt")
        self.assertIsNotNone(style_asf)
        self.assertEqual(style_asf.fill_color.name(), '#333333')

        # Sprawdzenie generowania ikony i pixmapy (swatch QPainter)
        icon = style_asf.get_icon(16)
        self.assertIsNotNone(icon)
        self.assertFalse(icon.isNull())
        pixmap = style_asf.get_pixmap(16)
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 16)
        self.assertEqual(pixmap.height(), 16)

        # Kategoria nieistniejąca w warstwie -> None (bez zgadywania)
        style_missing = find_category_style(styles, "kostka_brukowa")
        self.assertIsNone(style_missing)

    def test_category_style_info_swatch_generation(self):
        info = CategoryStyleInfo("Chodnik", QColor("#888888"), QColor("#333333"))
        icon = info.get_icon(24)
        self.assertIsNotNone(icon)
        self.assertFalse(icon.isNull())
        pix = info.get_pixmap(24)
        self.assertIsNotNone(pix)
        self.assertFalse(pix.isNull())
        self.assertEqual(pix.width(), 24)
        self.assertEqual(pix.height(), 24)

    def test_empty_layer_with_categorized_renderer_unique_categories(self):
        # Sprawdzamy czy na nowej, pustej warstwie zdefiniowane kategorie są od razu widoczne
        cat_layer = QgsVectorLayer("Polygon?crs=EPSG:2180", "EmptyStyled", "memory")
        cat_layer.dataProvider().addAttributes([
            QgsField("kategoria", QVariant.String)
        ])
        cat_layer.updateFields()

        sym1 = QgsFillSymbol.createSimple({'color': '#333333'})
        sym2 = QgsFillSymbol.createSimple({'color': '#28a745'})
        sym3 = QgsFillSymbol.createSimple({'color': '#c1121f'})

        cats = [
            QgsRendererCategory('trawa', sym2, 'Trawa'),
            QgsRendererCategory('asfalt', sym1, 'Asfalt'),
            QgsRendererCategory('ddr', sym3, 'DDR'),
        ]
        cat_layer.setRenderer(QgsCategorizedSymbolRenderer('kategoria', cats))

        # Warstwa nie ma żadnych obiektów (count = 0)
        self.assertEqual(cat_layer.featureCount(), 0)

        # Powinny zostać odczytane kategorie ze stylizacji i posortowane alfabetycznie
        unique_cats = get_layer_unique_categories(cat_layer)
        self.assertEqual(unique_cats, ["asfalt", "ddr", "trawa"])

    def test_find_polygon_feature_at_point(self):
        f = QgsFeature(self.layer.fields())
        f.setAttributes([1, "asfalt"])
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 10, 10)))
        self.layer.addFeature(f)

        pt_inside = QgsPointXY(5.0, 5.0)
        feat = find_polygon_feature_at_point(self.layer, pt_inside)
        self.assertIsNotNone(feat)
        self.assertEqual(feat.attribute("kategoria"), "asfalt")

        # Punkt poza poligonem
        pt_outside = QgsPointXY(50.0, 50.0)
        feat_none = find_polygon_feature_at_point(self.layer, pt_outside)
        self.assertIsNone(feat_none)

    def test_erase_polygon_with_radius_partial(self):
        # Poligon 10x10, powierzchnia początkowa = 100
        f = QgsFeature(self.layer.fields())
        f.setAttributes([1, "asfalt"])
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 10, 10)))
        self.layer.addFeature(f)

        feat = find_polygon_feature_at_point(self.layer, QgsPointXY(5.0, 5.0))
        self.assertIsNotNone(feat)
        orig_area = feat.geometry().area()
        self.assertAlmostEqual(orig_area, 100.0, delta=0.1)

        # Wycinek kołem w narożniku (0,0) o promieniu 2.0 (ćwiartka koła)
        success = erase_polygon_with_radius(self.layer, feat.id(), QgsPointXY(0.0, 0.0), 2.0)
        self.assertTrue(success)

        # Obiekt powinien nadal istnieć, ale mieć mniejsze pole powierzchni
        updated_feat = self.layer.getFeature(feat.id())
        self.assertTrue(updated_feat.isValid())
        new_area = updated_feat.geometry().area()
        self.assertLess(new_area, orig_area)
        # Oczekiwana redukcja ~ pi * 2^2 / 4 = pi ~ 3.14159
        self.assertAlmostEqual(orig_area - new_area, 3.14159, delta=0.2)
        self.assertTrue(updated_feat.geometry().isGeosValid())

    def test_erase_polygon_with_radius_full_delete(self):
        # Dodajemy mały poligon 2x2
        small_layer = QgsVectorLayer("Polygon?crs=EPSG:2180", "SmallLayer", "memory")
        small_layer.startEditing()
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 2, 2)))
        small_layer.addFeature(f)
        self.assertEqual(small_layer.featureCount(), 1)

        feat_id = [ft.id() for ft in small_layer.getFeatures()][0]

        # Wycinamy dyskiem o promieniu 10.0 wokół (1,1) - obejmuje cały poligon
        success = erase_polygon_with_radius(small_layer, feat_id, QgsPointXY(1.0, 1.0), 10.0)
        self.assertTrue(success)
        self.assertEqual(small_layer.featureCount(), 0)

    def test_erase_polygon_single_part_splitting(self):
        # Warstwa jednoelementowa SinglePart
        single_layer = QgsVectorLayer("Polygon?crs=EPSG:2180", "SinglePartLayer", "memory")
        pr = single_layer.dataProvider()
        pr.addAttributes([QgsField("kategoria", QVariant.String)])
        single_layer.updateFields()
        single_layer.startEditing()

        # Długi prostokąt od x=0 do x=20, y=-2 do y=2
        f = QgsFeature(single_layer.fields())
        f.setAttribute("kategoria", "jezdnia")
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, -2, 20, 2)))
        single_layer.addFeature(f)
        self.assertEqual(single_layer.featureCount(), 1)

        feat_id = [ft.id() for ft in single_layer.getFeatures()][0]

        # Wycinamy dyskiem o promieniu 3.0 w środku (10, 0)
        # Ponieważ wysokość to 4 (od -2 do 2), promień 3.0 w pełni przecina prostokąt w poprzek!
        success = erase_polygon_with_radius(single_layer, feat_id, QgsPointXY(10.0, 0.0), 3.0)
        self.assertTrue(success)

        # Warstwa SinglePart powinna teraz zawierać 2 obiekty (lewy i prawy fragment)
        features = list(single_layer.getFeatures())
        self.assertEqual(len(features), 2)
        for ft in features:
            self.assertEqual(ft.attribute("kategoria"), "jezdnia")
            self.assertTrue(ft.geometry().isGeosValid())
            self.assertGreater(ft.geometry().area(), 0)

    def test_erase_polygon_outside_no_change(self):
        f = QgsFeature(self.layer.fields())
        f.setAttributes([1, "asfalt"])
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 10, 10)))
        self.layer.addFeature(f)

        feat = find_polygon_feature_at_point(self.layer, QgsPointXY(5.0, 5.0))
        self.assertIsNotNone(feat)
        orig_area = feat.geometry().area()

        # Dysk daleko poza poligonem
        success = erase_polygon_with_radius(self.layer, feat.id(), QgsPointXY(100.0, 100.0), 5.0)
        self.assertFalse(success)
        self.assertAlmostEqual(self.layer.getFeature(feat.id()).geometry().area(), orig_area)


if __name__ == '__main__':
    unittest.main()


