from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

import flet as ft


SPI_GETCLIENTAREAANIMATION = 0x1042


def system_animations_enabled() -> bool:
    """Respeita silenciosamente a preferencia de movimento do Windows."""

    if sys.platform != "win32":
        return True
    enabled = ctypes.c_bool(True)
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
    except (AttributeError, OSError):
        return True
    return bool(enabled.value) if ok else True


@dataclass(frozen=True)
class MotionSystem:
    enabled: bool
    quick_ms: int
    standard_ms: int
    deliberate_ms: int

    @classmethod
    def from_system(cls) -> "MotionSystem":
        enabled = system_animations_enabled()
        return cls(
            enabled=enabled,
            quick_ms=130 if enabled else 0,
            standard_ms=210 if enabled else 0,
            deliberate_ms=320 if enabled else 0,
        )

    def quick(self) -> ft.Animation:
        return ft.Animation(self.quick_ms, ft.AnimationCurve.EASE_OUT_CUBIC)

    def standard(self) -> ft.Animation:
        return ft.Animation(self.standard_ms, ft.AnimationCurve.EASE_OUT_CUBIC)

    def deliberate(self) -> ft.Animation:
        return ft.Animation(self.deliberate_ms, ft.AnimationCurve.EASE_IN_OUT_CUBIC)
