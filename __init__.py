#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Punkt wejściowy fabryki wtyczki QGIS.
Autor: Mikołaj Sazonov
"""


def classFactory(iface):
    """
    Funkcja fabryczna wymagana przez QGIS do załadowania wtyczki.
    """
    from .plugin import MSACurveMasterPlugin
    return MSACurveMasterPlugin(iface)
