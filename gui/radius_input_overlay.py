#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Pływający widget wprowadzania promienia (CAD-style).
Autor: Mikołaj Sazonov
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal, QPoint
from qgis.PyQt.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame
)
from qgis.PyQt.QtGui import QDoubleValidator, QFont


class RadiusInputOverlay(QFrame):
    """
    Pływający widget CAD wyświetlający aktualny promień łuku w trakcie przeciągania
    oraz umożliwiający bezpośrednie wpisanie wartości z klawiatury (limit do 10 000 m).
    """

    radiusSubmitted = pyqtSignal(float)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        # Stylistyka CAD: zaokrąglone narożniki, ciemny półprzezroczysty styl
        self.setStyleSheet("""
            RadiusInputOverlay {
                background-color: rgba(33, 37, 41, 230);
                border: 1.5px solid #0d6efd;
                border-radius: 6px;
            }
            QLabel {
                color: #f8f9fa;
                font-weight: bold;
                font-size: 12px;
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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.label = QLabel("Promień:")
        layout.addWidget(self.label)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("np. 15.0")
        validator = QDoubleValidator(0.05, 10000.0, 2, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.edit.setValidator(validator)
        self.edit.returnPressed.connect(self._on_submit)
        layout.addWidget(self.edit)

        self.lbl_unit = QLabel("m")
        layout.addWidget(self.lbl_unit)

        self.lbl_hint = QLabel("(Enter = zatwierdź)")
        self.lbl_hint.setStyleSheet("color: #adb5bd; font-size: 10px; font-weight: normal;")
        layout.addWidget(self.lbl_hint)

        self.adjustSize()
        self.hide()

    def set_current_radius(self, radius: float):
        """Aktualizuje podgląd promienia jeśli użytkownik sam aktualnie nie pisze tekstu."""
        if not self.edit.hasFocus() and not self.edit.text().strip():
            clamped = min(max(0.05, radius), 10000.0)
            self.edit.setPlaceholderText(f"{clamped:.2f}")

    def update_position(self, screen_pos: QPoint, canvas_rect):
        """Ustawia pozycję widgetu obok kursora, dbając by nie wyszedł poza płótno mapy."""
        offset_x = 20
        offset_y = 20

        new_x = screen_pos.x() + offset_x
        new_y = screen_pos.y() + offset_y

        # Sprawdzenie granic canvas
        if new_x + self.width() > canvas_rect.width():
            new_x = screen_pos.x() - self.width() - offset_x
        if new_y + self.height() > canvas_rect.height():
            new_y = screen_pos.y() - self.height() - offset_y

        self.move(max(5, new_x), max(5, new_y))

    def activate_with_text(self, initial_char: str):
        """Aktywuje pole tekstowe z początkowym znakiem wpisanym z klawiatury."""
        self.show()
        self.edit.setText(initial_char)
        self.edit.setFocus()
        self.edit.setCursorPosition(len(initial_char))

    def _on_submit(self):
        text = self.edit.text().replace(',', '.').strip()
        try:
            val = float(text)
            if val > 0:
                clamped_val = min(val, 10000.0)
                self.radiusSubmitted.emit(clamped_val)
        except ValueError:
            pass

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.hide()
        else:
            super().keyPressEvent(e)
