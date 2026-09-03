#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Pływający widget CAD dla Polar Trackingu (Długość & Kąt).
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


class PolarInputOverlay(QFrame):
    """
    Pływający widget CAD wyświetlający aktualną długość odcinka i kąt śledzenia polarnego
    oraz umożliwiający wpisanie dokładnej długości z klawiatury i zatwierdzenie Enter/Tab.
    """

    distanceSubmitted = pyqtSignal(float)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_snapped: bool = False
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            PolarInputOverlay {
                background-color: rgba(30, 34, 42, 235);
                border: 1.5px solid #0d6efd;
                border-radius: 6px;
            }
            QLabel {
                color: #f8f9fa;
                font-weight: bold;
                font-size: 11px;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 1px 5px;
                font-weight: bold;
                font-size: 11px;
                min-width: 60px;
            }
            QLineEdit:focus {
                border: 1.5px solid #ffc107;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        self.lbl_len_title = QLabel("Dł:")
        layout.addWidget(self.lbl_len_title)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("0.00")
        validator = QDoubleValidator(0.001, 100000.0, 3, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.edit.setValidator(validator)
        self.edit.returnPressed.connect(self._on_submit)
        self.edit.installEventFilter(self)
        layout.addWidget(self.edit)

        self.lbl_unit = QLabel("m")
        layout.addWidget(self.lbl_unit)

        self.lbl_angle = QLabel("∠ 0.0°")
        self.lbl_angle.setStyleSheet("color: #adb5bd; font-size: 11px;")
        layout.addWidget(self.lbl_angle)

        self.lbl_snap_tag = QLabel("")
        self.lbl_snap_tag.setStyleSheet("color: #00e676; font-size: 10px; font-weight: bold;")
        layout.addWidget(self.lbl_snap_tag)

        self.adjustSize()
        self.hide()

    def update_info(
        self,
        length: float,
        map_angle: float,
        rel_angle: Optional[float] = None,
        is_polar_snapped: bool = False,
        badge_text: Optional[str] = None
    ):
        """Aktualizuje wartości długości i kąta w okienku CAD."""
        if not self.edit.hasFocus() and not self.edit.text().strip():
            self.edit.setPlaceholderText(f"{length:.2f}")

        if is_polar_snapped:
            self.setStyleSheet("""
                PolarInputOverlay {
                    background-color: rgba(20, 38, 25, 240);
                    border: 1.8px solid #00e676;
                    border-radius: 6px;
                }
                QLabel { color: #f8f9fa; font-weight: bold; font-size: 11px; }
                QLineEdit {
                    background-color: #ffffff; color: #000000;
                    border: 1px solid #ced4da; border-radius: 4px;
                    padding: 1px 5px; font-weight: bold; font-size: 11px; min-width: 60px;
                }
                QLineEdit:focus { border: 1.5px solid #ffc107; }
            """)
            self.lbl_angle.setText(f"∠ {map_angle:.1f}°")
            if badge_text:
                self.lbl_snap_tag.setText(badge_text)
            elif rel_angle is not None:
                self.lbl_snap_tag.setText(f"[Polar: {rel_angle:.1f}°]")
            else:
                self.lbl_snap_tag.setText("[Polar]")
        else:
            self.setStyleSheet("""
                PolarInputOverlay {
                    background-color: rgba(30, 34, 42, 235);
                    border: 1.5px solid #0d6efd;
                    border-radius: 6px;
                }
                QLabel { color: #f8f9fa; font-weight: bold; font-size: 11px; }
                QLineEdit {
                    background-color: #ffffff; color: #000000;
                    border: 1px solid #ced4da; border-radius: 4px;
                    padding: 1px 5px; font-weight: bold; font-size: 11px; min-width: 60px;
                }
                QLineEdit:focus { border: 1.5px solid #ffc107; }
            """)
            self.lbl_angle.setText(f"∠ {map_angle:.1f}°")
            self.lbl_snap_tag.setText("")

    def update_position(self, screen_pos: QPoint, canvas_rect):
        """Ustawia pozycję widgetu obok kursora."""
        offset_x = 22
        offset_y = 22

        new_x = screen_pos.x() + offset_x
        new_y = screen_pos.y() + offset_y

        if new_x + self.width() > canvas_rect.width():
            new_x = screen_pos.x() - self.width() - offset_x
        if new_y + self.height() > canvas_rect.height():
            new_y = screen_pos.y() - self.height() - offset_y

        self.move(max(5, new_x), max(5, new_y))

    def activate_with_text(self, initial_char: str):
        """Aktywuje pole tekstowe z wpisanym pierwszym znakiem."""
        self.show()
        self.edit.setText(initial_char)
        self.edit.setFocus()
        self.edit.setCursorPosition(len(initial_char))

    def _on_submit(self):
        """Zatwierdzenie wpisanej długości klawiszem Enter lub Tab."""
        text = self.edit.text().replace(',', '.').strip()
        if text:
            try:
                val = float(text)
                if val > 0:
                    self.distanceSubmitted.emit(val)
                    self.edit.clear()
                    return
            except ValueError:
                pass

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
