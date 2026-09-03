#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Model stanu i konfiguracji Polar Trackingu (CAD).
Autor: Mikołaj Sazonov
"""

from enum import Enum
from typing import List
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt import sip
from qgis.core import QgsSettings


class PolarAngleMeasurement(Enum):
    """Baza odniesienia pomiaru kąta polarnego."""
    RELATIVE = "relative"   # Względny do poprzedniego odcinka / krawędzi początkowej
    ABSOLUTE = "absolute"   # Bezwzględny względem osi X (układ współrzędnych)


# 11 standardowych presetów kroków kątowych z CAD i QGIS
POLAR_INCREMENT_PRESETS = [
    0.1,
    0.5,
    1.0,
    5.0,
    10.0,
    15.0,
    18.0,
    22.5,
    30.0,
    45.0,
    90.0
]


def format_preset_label(step: float) -> str:
    """Tworzy czytelną etykietę CAD dla kroku kątowego, np. '15.0, 30.0, 45.0, 60.0°...'"""
    s1 = step
    s2 = step * 2
    s3 = step * 3
    s4 = step * 4
    if step >= 1.0 and float(step).is_integer():
        return f"{int(s1)}, {int(s2)}, {int(s3)}, {int(s4)}°..."
    return f"{s1:.1f}, {s2:.1f}, {s3:.1f}, {s4:.1f}°..."


class PolarState(QObject):
    """
    Współdzielony model stanu Polar Trackingu.
    Przechowuje konfigurację, synchronizuje widżety UI i zapisuje preferencje w QgsSettings.
    """

    stateChanged = pyqtSignal()

    _instance = None

    @classmethod
    def instance(cls) -> 'PolarState':
        if cls._instance is None or sip.isdeleted(cls._instance):
            cls._instance = PolarState()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled: bool = True
        self._increment_angle: float = 15.0
        self._measurement_mode: PolarAngleMeasurement = PolarAngleMeasurement.RELATIVE
        self._additional_angles_enabled: bool = False
        self._additional_angles: List[float] = []
        self._tolerance_deg: float = 4.0
        self.load_settings()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool):
        if self._enabled != val:
            self._enabled = val
            self.save_settings()
            self.stateChanged.emit()

    @property
    def increment_angle(self) -> float:
        return self._increment_angle

    @increment_angle.setter
    def increment_angle(self, val: float):
        if self._increment_angle != val and val > 0:
            self._increment_angle = val
            self.save_settings()
            self.stateChanged.emit()

    @property
    def measurement_mode(self) -> PolarAngleMeasurement:
        return self._measurement_mode

    @measurement_mode.setter
    def measurement_mode(self, mode: PolarAngleMeasurement):
        if self._measurement_mode != mode:
            self._measurement_mode = mode
            self.save_settings()
            self.stateChanged.emit()

    @property
    def additional_angles_enabled(self) -> bool:
        return self._additional_angles_enabled

    @additional_angles_enabled.setter
    def additional_angles_enabled(self, val: bool):
        if self._additional_angles_enabled != val:
            self._additional_angles_enabled = val
            self.save_settings()
            self.stateChanged.emit()

    @property
    def additional_angles(self) -> List[float]:
        return list(self._additional_angles)

    @additional_angles.setter
    def additional_angles(self, angles: List[float]):
        cleaned = sorted(list(set(angles)))
        if self._additional_angles != cleaned:
            self._additional_angles = cleaned
            self.save_settings()
            self.stateChanged.emit()

    def add_additional_angle(self, angle: float):
        angle_norm = angle % 360.0
        if angle_norm not in self._additional_angles:
            self._additional_angles.append(angle_norm)
            self._additional_angles.sort()
            self.save_settings()
            self.stateChanged.emit()

    def remove_additional_angle(self, angle: float):
        if angle in self._additional_angles:
            self._additional_angles.remove(angle)
            self.save_settings()
            self.stateChanged.emit()

    @property
    def tolerance_deg(self) -> float:
        return self._tolerance_deg

    @tolerance_deg.setter
    def tolerance_deg(self, val: float):
        if self._tolerance_deg != val and val > 0:
            self._tolerance_deg = val
            self.save_settings()
            self.stateChanged.emit()

    def get_active_additional_angles(self) -> List[float]:
        """Zwraca listę dodatkowych kątów tylko jeśli są włączone."""
        if self._additional_angles_enabled:
            return self.additional_angles
        return []

    def save_settings(self):
        s = QgsSettings()
        s.setValue("msa_curvemaster/polar/enabled", self._enabled)
        s.setValue("msa_curvemaster/polar/increment", self._increment_angle)
        s.setValue("msa_curvemaster/polar/mode", self._measurement_mode.value)
        s.setValue("msa_curvemaster/polar/add_enabled", self._additional_angles_enabled)
        s.setValue("msa_curvemaster/polar/additional_angles", [str(a) for a in self._additional_angles])
        s.setValue("msa_curvemaster/polar/tolerance", self._tolerance_deg)

    def load_settings(self):
        s = QgsSettings()
        self._enabled = s.value("msa_curvemaster/polar/enabled", True, type=bool)
        self._increment_angle = s.value("msa_curvemaster/polar/increment", 15.0, type=float)
        mode_val = s.value("msa_curvemaster/polar/mode", "relative", type=str)
        self._measurement_mode = PolarAngleMeasurement.ABSOLUTE if mode_val == "absolute" else PolarAngleMeasurement.RELATIVE
        self._additional_angles_enabled = s.value("msa_curvemaster/polar/add_enabled", False, type=bool)
        raw_angles = s.value("msa_curvemaster/polar/additional_angles", [], type=list)
        parsed = []
        for a in raw_angles:
            try:
                parsed.append(float(a))
            except (ValueError, TypeError):
                pass
        self._additional_angles = sorted(list(set(parsed)))
        self._tolerance_deg = s.value("msa_curvemaster/polar/tolerance", 4.0, type=float)
