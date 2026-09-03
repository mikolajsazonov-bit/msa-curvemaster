# -*- coding: utf-8 -*-
"""
Internationalization (i18n) helper for MSA: CurveMaster.
Provides bilingual strings (English default, Polish when QGIS runs in Polish).
"""
from qgis.PyQt.QtCore import QCoreApplication, QSettings, QLocale


def is_polish_locale() -> bool:
    """Sprawdza czy interfejs QGIS jest w języku polskim."""
    try:
        loc = QSettings().value('locale/userLocale', '')
        if not loc:
            loc = QLocale.system().name()
        return str(loc).lower().startswith('pl')
    except Exception:
        return False


def tr(text_en: str, text_pl: str = None, context: str = 'MSACurveMaster') -> str:
    """
    Zwraca tekst w języku polskim jeśli interfejs QGIS jest po polsku,
    w przeciwnym wypadku tekst po angielsku.
    """
    if is_polish_locale() and text_pl:
        return text_pl
    return QCoreApplication.translate(context, text_en)
