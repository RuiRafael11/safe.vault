from __future__ import annotations

import unittest

import flet as ft

from cofre_local.ui_flet.components import (
    credential_row,
    glass_card,
    glass_text_field,
    pill_button,
    security_badge,
)
from cofre_local.ui_flet.motion import MotionSystem
from cofre_local.ui_flet.theme import get_palette


class ComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.palette = get_palette("pearl")
        self.motion = MotionSystem(True, 130, 210, 320)

    def test_glass_components_construct_for_every_theme(self) -> None:
        for theme in ("pearl", "midnight", "aurora", "graphite"):
            palette = get_palette(theme)
            self.assertIsInstance(glass_card(ft.Text("x"), palette), ft.Container)
            self.assertIsInstance(security_badge(palette), ft.Container)
            self.assertIsInstance(pill_button("Guardar", palette, None, primary=True), ft.Button)
            self.assertIsInstance(glass_text_field(palette, label="Nome"), ft.TextField)

    def test_credential_row_never_displays_password(self) -> None:
        entry = {
            "title": "Conta",
            "username": "pessoa@example.com",
            "password": "segredo-que-nao-pode-aparecer",
            "category": "Pessoal",
            "favorite": True,
        }
        row = credential_row(entry, self.palette, self.motion, selected=True, on_click=lambda _e: None)
        rendered = repr(row)
        self.assertNotIn(entry["password"], rendered)
        self.assertIn(entry["title"], rendered)


if __name__ == "__main__":
    unittest.main()
