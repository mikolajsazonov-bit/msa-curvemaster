#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
***************************************************************************
*   MSA: CurveMaster - Pływający widget wprowadzania promienia wylewania  *
*   oraz szybkiego wyboru kategorii nawierzchni (CAD HUD).                *
*   Autor: Mikołaj Sazonov                                                *
***************************************************************************
"""

from typing import Optional
from qgis.PyQt.QtCore import Qt, pyqtSignal, QPoint, QEvent
from qgis.PyQt.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame
)
from qgis.PyQt.QtGui import QDoubleValidator
try:
    from ..core.i18n import tr
except (ImportError, ValueError):
    from core.i18n import tr


class PourInputOverlay(QFrame):
    """
    Pływający widget CAD wyświetlający aktualny promień odcięcia wylewania (zasięg)
    oraz aktywną kategorię nawierzchni.
    Umożliwia cykliczne przełączanie kategorii klawiszem Tab oraz wpisanie promienia z klawiatury.
    """

    radiusSubmitted = pyqtSignal(float)
    categoryCycleRequested = pyqtSignal()
    categoryCyclePrevRequested = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_radius: Optional[float] = None
        self._current_radius: float = 0.0
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            PourInputOverlay {
                background-color: rgba(33, 37, 41, 240);
                border: 1.5px solid #0d6efd;
                border-radius: 6px;
            }
            QLabel {
                color: #f8f9fa;
                font-size: 11px;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 2px 6px;
                font-weight: bold;
                font-size: 12px;
                min-width: 65px;
            }
            QLineEdit:focus {
                border: 1.5px solid #ffc107;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(4)

        # Wiersz 1: Promień / Zasięg
        row_radius = QHBoxLayout()
        row_radius.setContentsMargins(0, 0, 0, 0)
        row_radius.setSpacing(6)

        lbl_radius = QLabel(tr("Zasięg:", "Zasięg:"))
        lbl_radius.setStyleSheet("font-weight: bold; color: #ffffff;")
        row_radius.addWidget(lbl_radius)

        self.edit_radius = QLineEdit()
        self.edit_radius.setPlaceholderText("np. 50.0")
        validator = QDoubleValidator(0.1, 10000.0, 2, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.edit_radius.setValidator(validator)
        self.edit_radius.returnPressed.connect(self._on_submit)
        self.edit_radius.installEventFilter(self)
        row_radius.addWidget(self.edit_radius)

        lbl_unit = QLabel("m")
        lbl_unit.setStyleSheet("font-weight: bold;")
        row_radius.addWidget(lbl_unit)

        self.lbl_hint = QLabel("(Enter = zatwierdź)")
        self.lbl_hint.setStyleSheet("color: #adb5bd; font-size: 10px;")
        row_radius.addWidget(self.lbl_hint)
        main_layout.addLayout(row_radius)

        # Wiersz 2: Kategoria i wskazówka Tab
        row_cat = QHBoxLayout()
        row_cat.setContentsMargins(0, 0, 0, 0)
        row_cat.setSpacing(6)

        lbl_cat_title = QLabel(tr("Kategoria:", "Kategoria:"))
        lbl_cat_title.setStyleSheet("font-weight: bold; color: #ffffff;")
        row_cat.addWidget(lbl_cat_title)

        self.lbl_cat_swatch = QLabel()
        self.lbl_cat_swatch.setFixedSize(16, 16)
        self.lbl_cat_swatch.setStyleSheet("background: transparent;")
        self.lbl_cat_swatch.hide()
        row_cat.addWidget(self.lbl_cat_swatch)

        self.lbl_cat_val = QLabel("Asfalt")
        self.lbl_cat_val.setStyleSheet("""
            background-color: #0d6efd;
            color: #ffffff;
            font-weight: bold;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 4px;
        """)
        row_cat.addWidget(self.lbl_cat_val)

        self.lbl_tab_hint = QLabel("(Tab = zmień)")
        self.lbl_tab_hint.setStyleSheet("color: #ffc107; font-size: 10px; font-weight: bold;")
        row_cat.addWidget(self.lbl_tab_hint)
        row_cat.addStretch()

        main_layout.addLayout(row_cat)

        self.adjustSize()
        self.hide()

    def set_last_radius(self, radius: Optional[float]):
        """Ustawia zapamiętany ostatni promień."""
        self.last_radius = radius
        if radius is not None and radius > 0:
            self.lbl_hint.setText(f"(Enter = <{radius:.2f}> m)")
            if not self.edit_radius.hasFocus() and not self.edit_radius.text().strip():
                self.edit_radius.setPlaceholderText(f"<{radius:.2f}>")
        else:
            self.lbl_hint.setText("(Enter = zatwierdź)")
            self.edit_radius.setPlaceholderText("np. 50.0")

    def set_category_name(self, name: str, style: Optional[object] = None):
        """Aktualizuje etykietę i kolorystykę aktywnej kategorii ze stylizacji warstwy."""
        clean_name = name.strip() if name else "Brak"
        self.lbl_cat_val.setText(clean_name)

        if style is not None and hasattr(style, 'fill_color'):
            # Stylizacja bezpośrednio z warstwy QGIS
            fill_hex = style.fill_color.name()
            stroke_hex = style.stroke_color.name() if style.stroke_color else fill_hex
            text_hex = style.text_color.name() if style.text_color else "#ffffff"

            self.lbl_cat_val.setStyleSheet(f"""
                background-color: {fill_hex};
                color: {text_hex};
                font-weight: bold;
                font-size: 11px;
                padding: 2px 8px;
                border: 1.5px solid {stroke_hex};
                border-radius: 4px;
            """)

            pixmap = style.get_pixmap(16) if hasattr(style, 'get_pixmap') else None
            if pixmap and not pixmap.isNull():
                self.lbl_cat_swatch.setPixmap(pixmap)
                self.lbl_cat_swatch.show()
            else:
                self.lbl_cat_swatch.hide()

        elif clean_name.startswith("[") or "nowa" in clean_name.lower():
            self.lbl_cat_swatch.hide()
            self.lbl_cat_val.setStyleSheet("""
                background-color: #198754;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 2px 8px;
                border: 1.5px solid #28a745;
                border-radius: 4px;
            """)
        else:
            # Domyślny neutralny styl (brak stylizacji w warstwie - bez zgadywania)
            self.lbl_cat_swatch.hide()
            self.lbl_cat_val.setStyleSheet("""
                background-color: #0d6efd;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 2px 8px;
                border: 1.5px solid #0b5ed7;
                border-radius: 4px;
            """)

        self.adjustSize()

    def update_values(self, radius: float, category_name: str, pos: QPoint, style: Optional[object] = None):
        """Aktualizuje wyświetlany promień w czasie przeciągania oraz pozycję widgetu."""
        self._current_radius = radius
        self.set_category_name(category_name, style)
        if not self.edit_radius.hasFocus():
            self.edit_radius.setText(f"{radius:.2f}")

        # Pozycjonowanie obok kursora (odsunięcie w prawo i w dół)
        offset_pos = pos + QPoint(20, 20)
        parent = self.parentWidget()
        if parent:
            max_x = parent.width() - self.width() - 10
            max_y = parent.height() - self.height() - 10
            x = max(10, min(offset_pos.x(), max_x))
            y = max(10, min(offset_pos.y(), max_y))
            self.move(x, y)
        else:
            self.move(offset_pos)

        if not self.isVisible():
            self.show()

    def _on_submit(self):
        text = self.edit_radius.text().strip().replace(',', '.')
        val = None
        try:
            val = float(text)
        except ValueError:
            val = None

        if val is not None and val > 0:
            self.radiusSubmitted.emit(val)
            return

        if self.last_radius is not None and self.last_radius > 0:
            self.radiusSubmitted.emit(self.last_radius)
        elif self._current_radius > 0:
            self.radiusSubmitted.emit(self._current_radius)

    def eventFilter(self, obj, event):
        if obj == self.edit_radius and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Tab:
                if event.modifiers() & Qt.ShiftModifier:
                    self.categoryCyclePrevRequested.emit()
                else:
                    self.categoryCycleRequested.emit()
                return True
            elif key == Qt.Key_Backtab:
                self.categoryCyclePrevRequested.emit()
                return True
            elif key == Qt.Key_Escape:
                self.cancelled.emit()
                return True

        return super().eventFilter(obj, event)
