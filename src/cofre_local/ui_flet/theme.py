from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class AppPalette:
    """Tokens visuais de um tema do Cofre Local."""

    key: str
    name: str
    dark: bool
    background: str
    background_secondary: str
    atmospheric: str
    glass: str
    glass_strong: str
    sidebar: str
    text: str
    muted: str
    accent: str
    accent_soft: str
    success: str
    warning: str
    danger: str
    border: str
    shadow: str


PALETTES: dict[str, AppPalette] = {
    "pearl": AppPalette(
        key="pearl",
        name="Pearl",
        dark=False,
        background="#F7F7F7",
        background_secondary="#F2F2F2",
        atmospheric="#EFEFEF",
        glass="#FAFAFA",
        glass_strong="#FFFFFF",
        sidebar="#F0F0F0",
        text="#292929",
        muted="#666666",
        accent="#438FE5",
        accent_soft=ft.Colors.with_opacity(0.13, "#438FE5"),
        success="#2FA876",
        warning="#E5A30A",
        danger="#C94B5E",
        border="#DCDCDC",
        shadow=ft.Colors.with_opacity(0.14, "#30344A"),
    ),
    "midnight": AppPalette(
        key="midnight",
        name="Midnight",
        dark=True,
        background="#171717",
        background_secondary="#191919",
        atmospheric="#202020",
        glass="#1C1C1C",
        glass_strong="#242424",
        sidebar="#141414",
        text="#EBEBEB",
        muted="#A3A3A3",
        accent="#4599F7",
        accent_soft=ft.Colors.with_opacity(0.18, "#4599F7"),
        success="#51C997",
        warning="#F2BB46",
        danger="#F07B8B",
        border=ft.Colors.with_opacity(0.11, "#FFFFFF"),
        shadow=ft.Colors.with_opacity(0.38, "#000000"),
    ),
    "aurora": AppPalette(
        key="aurora",
        name="Aurora",
        dark=False,
        background="#F1F6F7",
        background_secondary="#E4EFF4",
        atmospheric="#DCD8FF",
        glass=ft.Colors.with_opacity(0.61, "#FFFFFF"),
        glass_strong=ft.Colors.with_opacity(0.86, "#FFFFFF"),
        sidebar=ft.Colors.with_opacity(0.52, "#F1FAFA"),
        text="#152126",
        muted="#64757B",
        accent="#5268D8",
        accent_soft=ft.Colors.with_opacity(0.14, "#5268D8"),
        success="#258E72",
        warning="#D99A1E",
        danger="#C85267",
        border="#D6E0E2",
        shadow=ft.Colors.with_opacity(0.14, "#35566A"),
    ),
    "graphite": AppPalette(
        key="graphite",
        name="Graphite",
        dark=True,
        background="#181818",
        background_secondary="#202020",
        atmospheric="#242424",
        glass=ft.Colors.with_opacity(0.60, "#222222"),
        glass_strong=ft.Colors.with_opacity(0.86, "#262626"),
        sidebar=ft.Colors.with_opacity(0.66, "#141414"),
        text="#EBEBEB",
        muted="#A3A3A3",
        accent="#4599F7",
        accent_soft=ft.Colors.with_opacity(0.18, "#4599F7"),
        success="#63BF8E",
        warning="#DCA94D",
        danger="#E17A83",
        border=ft.Colors.with_opacity(0.10, "#FFFFFF"),
        shadow=ft.Colors.with_opacity(0.42, "#000000"),
    ),
}

DEFAULT_THEME = "midnight"


def get_palette(key: str | None) -> AppPalette:
    return PALETTES.get((key or "").lower(), PALETTES[DEFAULT_THEME])


def page_theme(palette: AppPalette) -> ft.Theme:
    """Neutral surfaces, restrained blue focus and local Inter typography."""

    return ft.Theme(
        color_scheme_seed=palette.accent,
        font_family="Inter",
        use_material3=True,
        scaffold_bgcolor=palette.background,
        canvas_color=palette.background,
        card_bgcolor=palette.glass,
        divider_color=palette.border,
        splash_color=ft.Colors.with_opacity(0.06, palette.accent),
        hover_color=ft.Colors.with_opacity(0.07, palette.accent),
        focus_color=ft.Colors.with_opacity(0.10, palette.accent),
        disabled_color=ft.Colors.with_opacity(0.35, palette.muted),
    )


def background_gradient(palette: AppPalette) -> ft.LinearGradient:
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_LEFT,
        end=ft.Alignment.BOTTOM_RIGHT,
        colors=[palette.background, palette.background],
        stops=[0.0, 1.0],
    )
