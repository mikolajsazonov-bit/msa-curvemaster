#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Pływający widget wprowadzania odległości offsetu (CAD-style).
Autor: Mikołaj Sazonov
"""

from typing import Optional
from qgis.PyQt.QtCore import Qt, pyqtSignal, QPoint, QEvent
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame
)
from qgis.PyQt.QtGui import QDoubleValidator


class OffsetInputOverlay(QFrame):
    """
    Pływający widget CAD wyświetlający aktualną odległość odsunięcia (offset) w trakcie przeciągania
    oraz umożliwiający bezpośrednie wpisanie wartości z klawiatury (do 100 000 m).
    Obsługuje powtarzanie poprzedniej odległości klawiszami Enter lub Tab.
    """

    distanceSubmitted = pyqtSignal(float)
    defaultDistanceRequested = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_distance: Optional[float] = None
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            OffsetInputOverlay {
                background-color: rgba(33, 37, 41, 235);
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

        self.label = QLabel("Odległość:")
        layout.addWidget(self.label)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("np. 5.0")
        validator = QDoubleValidator(0.001, 100000.0, 3, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.edit.setValidator(validator)
        self.edit.returnPressed.connect(self._on_submit)
        # Przechwytywanie klawisza Tab wewnątrz QLineEdit
        self.edit.installEventFilter(self)
        layout.addWidget(self.edit)

        self.lbl_unit = QLabel("m")
        layout.addWidget(self.lbl_unit)

        self.lbl_hint = QLabel("(Enter/Tab = zatwierdź)")
        self.lbl_hint.setStyleSheet("color: #adb5bd; font-size: 10px; font-weight: normal;")
        layout.addWidget(self.lbl_hint)

        self.adjustSize()
        self.hide()

    def set_last_distance(self, dist: Optional[float]):
        """Ustawia zapamiętaną ostatnią odległość i odświeża wskazówkę (CAD <default>)."""
        self.last_distance = dist
        if dist is not None and dist > 0:
            self.lbl_hint.setText(f"(Enter/Tab = <{dist:.2f}> m)")
            if not self.edit.hasFocus() and not self.edit.text().strip():
                self.edit.setPlaceholderText(f"<{dist:.2f}>")
        else:
            self.lbl_hint.setText("(Enter/Tab = zatwierdź)")
            if not self.edit.hasFocus() and not self.edit.text().strip():
                self.edit.setPlaceholderText("np. 5.0")

    def set_current_distance(self, dist: float):
        """Aktualizuje podgląd odległości jeśli użytkownik sam aktualnie nie pisze tekstu."""
        if not self.edit.hasFocus() and not self.edit.text().strip():
            if self.last_distance is not None and self.last_distance > 0:
                self.edit.setPlaceholderText(f"<{self.last_distance:.2f}> ({dist:.2f} m)")
            else:
                clamped = min(max(0.001, dist), 100000.0)
                self.edit.setPlaceholderText(f"{clamped:.2f}")

    def update_position(self, screen_pos: QPoint, canvas_rect):
        """Ustawia pozycję widgetu obok kursora, dbając by nie wyszedł poza płótno mapy."""
        offset_x = 20
        offset_y = 20

        new_x = screen_pos.x() + offset_x
        new_y = screen_pos.y() + offset_y

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
        """Zatwierdzenie wartości (Enter lub Tab)."""
        text = self.edit.text().replace(',', '.').strip()
        if text:
            try:
                val = float(text)
                if val > 0:
                    clamped_val = min(val, 100000.0)
                    self.distanceSubmitted.emit(clamped_val)
                    return
            except ValueError:
                pass

        # Jeśli brak wpisanego tekstu, ale mamy zapamiętaną poprzednią odległość
        if self.last_distance is not None and self.last_distance > 0:
            self.distanceSubmitted.emit(self.last_distance)
        else:
            self.defaultDistanceRequested.emit()

    def eventFilter(self, obj, event):
        if obj == self.edit and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                self._on_submit()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.hide()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            self._on_submit()
        else:
            super().keyPressEvent(e)
