from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from .motion import MotionSystem
from .theme import AppPalette


Callback = Callable[[Any], None]


def brand_mark(size: float = 48) -> ft.Image:
    """Shared vector identity: a vault door with a four-spoke dial."""
    return ft.Image(src="brand/cofre-mark.svg", width=size, height=size,
                    semantics_label="Cofre Local", fit=ft.BoxFit.CONTAIN)


def glass_shadow(palette: AppPalette, *, elevated: bool = False) -> ft.BoxShadow:
    return ft.BoxShadow(
        blur_radius=16 if elevated else 8,
        spread_radius=-6 if elevated else -8,
        color=palette.shadow,
        offset=ft.Offset(0, 4 if elevated else 2),
    )


def glass_card(
    content: ft.Control,
    palette: AppPalette,
    *,
    padding: int | ft.Padding = 20,
    radius: int = 14,
    strong: bool = False,
    elevated: bool = False,
    expand: bool | int | None = None,
    width: float | None = None,
    height: float | None = None,
    border_color: str | None = None,
    on_click: Callback | None = None,
    animate: ft.Animation | None = None,
) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=palette.glass_strong if strong else palette.glass,
        border=ft.Border.all(1, border_color or palette.border),
        border_radius=radius,
        shadow=glass_shadow(palette, elevated=True) if elevated else None,
        expand=expand,
        width=width,
        height=height,
        on_click=on_click,
        animate=animate,
    )


def pill_button(
    label: str,
    palette: AppPalette,
    on_click: Callback | None,
    *,
    icon: ft.IconData | None = None,
    primary: bool = False,
    danger: bool = False,
    width: float | None = None,
    disabled: bool = False,
) -> ft.Button:
    if primary:
        bgcolor = palette.text
        color = palette.background
    elif danger:
        bgcolor = ft.Colors.with_opacity(0.12, palette.danger)
        color = palette.danger
    else:
        bgcolor = palette.glass_strong
        color = palette.text
    return ft.Button(
        content=label,
        icon=icon,
        color=color,
        bgcolor=bgcolor,
        elevation=0,
        disabled=disabled,
        width=width,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            padding=ft.Padding.symmetric(horizontal=18, vertical=13),
            side=ft.BorderSide(1, palette.border),
            shadow_color=palette.shadow,
            animation_duration=140,
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_500, font_family="Inter"),
        ),
    )


def glass_icon_button(
    icon: ft.IconData,
    palette: AppPalette,
    on_click: Callback | None,
    *,
    tooltip: str,
    selected: bool = False,
) -> ft.IconButton:
    return ft.IconButton(
        icon=icon,
        icon_color=palette.accent if selected else palette.text,
        icon_size=19,
        bgcolor=palette.accent_soft if selected else palette.glass_strong,
        tooltip=tooltip,
        padding=12,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            side=ft.BorderSide(1, palette.border),
            animation_duration=130,
        ),
    )


def glass_text_field(
    palette: AppPalette,
    *,
    label: str | None = None,
    hint: str | None = None,
    value: str = "",
    password: bool = False,
    multiline: bool = False,
    prefix_icon: ft.IconData | None = None,
    suffix_icon: ft.IconData | None = None,
    on_change: Callback | None = None,
    on_submit: Callback | None = None,
    autofocus: bool = False,
    expand: bool | int | None = None,
) -> ft.TextField:
    return ft.TextField(
        value=value,
        label=label,
        hint_text=hint,
        password=password,
        can_reveal_password=password,
        multiline=multiline,
        min_lines=3 if multiline else None,
        max_lines=5 if multiline else 1,
        prefix_icon=prefix_icon,
        suffix_icon=suffix_icon,
        on_change=on_change,
        on_submit=on_submit,
        autofocus=autofocus,
        expand=expand,
        text_size=14,
        text_style=ft.TextStyle(font_family="Inter", color=palette.text),
        label_style=ft.TextStyle(font_family="Inter", color=palette.muted, size=13),
        hint_style=ft.TextStyle(font_family="Inter", color=palette.muted, size=14),
        filled=True,
        fill_color=palette.glass_strong,
        border=ft.InputBorder.OUTLINE,
        border_radius=10,
        border_width=1,
        border_color=palette.border,
        focused_border_color=palette.accent,
        focused_border_width=1.4,
        cursor_color=palette.accent,
        selection_color=palette.accent_soft,
        content_padding=ft.Padding.symmetric(horizontal=18, vertical=15),
    )


def security_badge(palette: AppPalette) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.GPP_GOOD_ROUNDED, color=palette.success, size=17),
                ft.Text(
                    "Cofre protegido",
                    color=palette.success,
                    size=13,
                    weight=ft.FontWeight.W_500,
                    font_family="Inter",
                ),
            ],
            spacing=8,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        bgcolor=ft.Colors.with_opacity(0.10, palette.success),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.18, palette.success)),
        border_radius=10,
    )


def nav_item(
    label: str,
    icon: ft.IconData,
    palette: AppPalette,
    *,
    selected: bool,
    on_click: Callback,
    motion: MotionSystem,
) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=20, color=palette.accent if selected else palette.text),
                ft.Text(
                    label,
                    size=14,
                    color=palette.text,
                    weight=ft.FontWeight.W_500 if selected else ft.FontWeight.W_400,
                    font_family="Inter",
                ),
            ],
            spacing=14,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=11),
        bgcolor=palette.accent_soft if selected else ft.Colors.TRANSPARENT,
        border=ft.Border.all(1, palette.border if selected else ft.Colors.TRANSPARENT),
        border_radius=10,
        on_click=on_click,
        animate=motion.quick(),
    )


def sidebar(
    palette: AppPalette,
    motion: MotionSystem,
    *,
    selected: str,
    auto_lock_minutes: int,
    on_select: Callable[[str], None],
    on_lock: Callback,
    on_settings: Callback,
) -> ft.Container:
    nav = [
        ("Todas", ft.Icons.GRID_VIEW_ROUNDED),
        ("Favoritos", ft.Icons.STAR_OUTLINE_ROUNDED),
        ("Pessoal", ft.Icons.PERSON_OUTLINE_ROUNDED),
        ("Trabalho", ft.Icons.WORK_OUTLINE_ROUNDED),
        ("Finanças", ft.Icons.CREDIT_CARD_ROUNDED),
        ("Redes sociais", ft.Icons.GROUP_OUTLINED),
        ("Compras", ft.Icons.SHOPPING_BAG_OUTLINED),
        ("Outros", ft.Icons.MORE_HORIZ_ROUNDED),
    ]
    return ft.Container(
        width=224,
        padding=18,
        bgcolor=palette.sidebar,
        border=ft.Border.all(1, palette.border),
        border_radius=14,
        content=ft.Column(
            [
                ft.Row(
                    [
                        brand_mark(40),
                        ft.Column(
                            [
                                ft.Text(
                                    "Cofre Local",
                                    size=14,
                                    weight=ft.FontWeight.W_600,
                                    color=palette.text,
                                    font_family="Inter",
                                ),
                                ft.Text("Espaço privado", size=11, color=palette.muted, font_family="Inter"),
                            ],
                            spacing=1,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Container(height=8),
                *[
                    nav_item(
                        label,
                        icon,
                        palette,
                        selected=selected == label,
                        on_click=lambda _e, value=label: on_select(value),
                        motion=motion,
                    )
                    for label, icon in nav
                ],
                ft.Container(expand=True),
                nav_item(
                    "Definições",
                    ft.Icons.TUNE_ROUNDED,
                    palette,
                    selected=selected == "Definições",
                    on_click=on_settings,
                    motion=motion,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.LOCK_OUTLINE_ROUNDED, size=19, color=palette.text),
                            ft.Text("Bloquear cofre", size=13, color=palette.text, font_family="Inter"),
                        ],
                        spacing=11,
                    ),
                    padding=ft.Padding.symmetric(horizontal=15, vertical=13),
                    bgcolor=palette.glass_strong,
                    border=ft.Border.all(1, palette.border),
                    border_radius=10,
                    on_click=on_lock,
                ),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SCHEDULE_ROUNDED, size=14, color=palette.muted),
                        ft.Text(
                            f"Bloqueio automático: {auto_lock_minutes} min",
                            size=10.5,
                            color=palette.muted,
                            font_family="Inter",
                        ),
                    ],
                    spacing=6,
                ),
            ],
            spacing=6,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def credential_row(
    entry: dict[str, Any],
    palette: AppPalette,
    motion: MotionSystem,
    *,
    selected: bool,
    on_click: Callback,
) -> ft.Container:
    title = str(entry.get("title", "Sem nome"))
    initial = title[:1].upper() or "?"
    favorite = bool(entry.get("favorite"))
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        initial,
                        size=18,
                        color=palette.text,
                        weight=ft.FontWeight.W_500,
                        font_family="Inter",
                    ),
                    width=46,
                    height=46,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=palette.glass_strong,
                    border=ft.Border.all(1, palette.border),
                    border_radius=15,
                ),
                ft.Column(
                    [
                        ft.Text(
                            title,
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=palette.text,
                            font_family="Inter",
                        ),
                        ft.Text(
                            str(entry.get("username", "")) or "Sem utilizador",
                            size=11.5,
                            color=palette.muted,
                            font_family="Inter",
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Text(
                        str(entry.get("category", "Outros")),
                        size=10.5,
                        color=palette.accent,
                        font_family="Inter",
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    bgcolor=palette.accent_soft,
                    border_radius=10,
                ),
                ft.Icon(
                    ft.Icons.STAR_ROUNDED if favorite else ft.Icons.STAR_OUTLINE_ROUNDED,
                    color=palette.warning if favorite else palette.muted,
                    size=19,
                ),
            ],
            spacing=13,
        ),
        padding=15,
        bgcolor=palette.accent_soft if selected else ft.Colors.TRANSPARENT,
        border=ft.Border.all(1, palette.border),
        border_radius=12,
        shadow=None,
        on_click=on_click,
        animate=motion.quick(),
    )


def detail_value(
    label: str,
    value: str,
    palette: AppPalette,
    *,
    secret: bool = False,
    on_copy: Callback | None = None,
    on_open: Callback | None = None,
    on_reveal: Callback | None = None,
    revealed: bool = False,
) -> ft.Column:
    shown = "•" * min(max(len(value), 10), 18) if secret and not revealed and value else value or "—"
    actions: list[ft.Control] = []
    if on_open:
        actions.append(glass_icon_button(ft.Icons.OPEN_IN_NEW_ROUNDED, palette, on_open, tooltip="Abrir"))
    if on_copy:
        actions.append(glass_icon_button(ft.Icons.CONTENT_COPY_ROUNDED, palette, on_copy, tooltip="Copiar"))
    if secret and on_reveal:
        actions.insert(0, glass_icon_button(ft.Icons.VISIBILITY_OFF_ROUNDED if revealed else ft.Icons.VISIBILITY_ROUNDED, palette, on_reveal, tooltip="Ocultar" if revealed else "Mostrar"))
    return ft.Column(
        [
            ft.Text(label, size=11.5, color=palette.muted, font_family="Inter"),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            shown,
                            size=13,
                            color=palette.text,
                            font_family="Inter" if not secret else "Consolas",
                            expand=True,
                            selectable=not secret or revealed,
                        ),
                        *actions,
                    ],
                    spacing=6,
                ),
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                bgcolor=palette.glass_strong,
                border=ft.Border.all(1, palette.border),
                border_radius=10,
            ),
        ],
        spacing=6,
    )


def empty_detail(palette: AppPalette) -> ft.Container:
    return glass_card(
        ft.Column(
            [
                ft.Icon(ft.Icons.KEY_ROUNDED, color=palette.accent, size=34),
                ft.Text(
                    "Selecione uma credencial",
                    size=16,
                    weight=ft.FontWeight.W_500,
                    color=palette.text,
                    font_family="Inter",
                ),
                ft.Text(
                    "Os detalhes aparecem aqui sem abrir outra janela.",
                    size=12,
                    color=palette.muted,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Inter",
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
            expand=True,
        ),
        palette,
        expand=True,
        strong=True,
    )
