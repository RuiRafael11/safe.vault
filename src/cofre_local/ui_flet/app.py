from __future__ import annotations

import asyncio
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import flet as ft

from cofre_local import __version__
from cofre_local.vault import (
    InvalidMasterPassword,
    InvalidVaultFile,
    VaultBusyError,
    VaultChangedError,
    VaultError,
    VaultSession,
    create,
    export_encrypted_copy,
    generate_password,
    new_entry,
    utc_now,
    wipe_key,
)

from .components import (
    brand_mark,
    credential_row,
    detail_value,
    empty_detail,
    glass_card,
    glass_icon_button,
    glass_text_field,
    pill_button,
    security_badge,
    sidebar,
)
from .motion import MotionSystem
from .preferences import load_preferences, save_preferences
from .theme import PALETTES, AppPalette, background_gradient, get_palette, page_theme


CATEGORIES = ("Pessoal", "Trabalho", "Finanças", "Redes sociais", "Compras", "Outros")
MIN_MASTER_PASSWORD = 12


def default_vault_path() -> Path:
    documents = Path.home() / "Documents"
    base = documents if documents.exists() else Path.home()
    return base / "Cofre Local" / "cofre.vault"


class CofreLocalFletApp:
    """Interface desktop principal do Cofre Local."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.preferences = load_preferences()
        self.palette = get_palette(str(self.preferences["theme"]))
        self.motion = MotionSystem.from_system()
        self.session: VaultSession | None = None
        self.selected_id: str | None = None
        self.selected_filter = "Todas"
        self.search_query = ""
        self.sort_mode = "Nome"
        self.last_activity = time.monotonic()
        self._closing = False
        self._clipboard_token = 0
        self._current_screen = "welcome"
        self._session_generation = 0
        self._operation_active: set[str] = set()
        self._password_revealed = False
        self._editor_sensitive_fields: list[ft.TextField] = []
        self._sensitive_fields: list[ft.TextField] = []
        self._editor_generation: int | None = None
        self._detached_closes: dict[int, VaultSession] = {}
        self._finishing_close_ids: set[int] = set()
        self._detached_close_event = asyncio.Event()
        self._detached_close_event.set()

        self.file_picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()
        self.page.services.extend([self.file_picker, self.clipboard])

        self._configure_page()
        self.switcher = ft.AnimatedSwitcher(
            content=ft.Container(expand=True),
            duration=self.motion.standard_ms,
            reverse_duration=self.motion.quick_ms,
            switch_in_curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            switch_out_curve=ft.AnimationCurve.EASE_IN_CUBIC,
            transition=ft.AnimatedSwitcherTransition.FADE,
            expand=True,
        )
        self.page.add(self.switcher)
        self.show_welcome()
        self.page.run_task(self._security_loop)
        if os.environ.get("COFRE_LOCAL_FLET_SMOKE") == "1":
            self.page.run_task(self._close_after_smoke_test)

    def _configure_page(self) -> None:
        self.page.title = "Cofre Local"
        # O produto é desktop; o renderer WebGL usado apenas nos testes visuais
        # não carrega de forma fiável fontes variáveis locais.
        if not self.page.web:
            self.page.fonts = {"Inter": "fonts/Inter-Variable.ttf"}
        self.page.theme = page_theme(self.palette)
        self.page.theme_mode = ft.ThemeMode.DARK if self.palette.dark else ft.ThemeMode.LIGHT
        self.page.window.width = 1180
        self.page.window.height = 760
        self.page.window.min_width = 940
        self.page.window.min_height = 620
        self.page.window.prevent_close = True
        self.page.window.on_event = self._on_window_event
        if not self.page.web:
            self.page.run_task(self.page.window.center)
        root_view = self.page.views[0]
        root_view.padding = 0
        root_view.spacing = 0
        root_view.bgcolor = self.palette.background
        self.page.on_keyboard_event = self._mark_activity
        # on_close is a session-expiration callback in Flet, not a desktop
        # window close. Native close is handled by WindowEvent.CLOSE above.
        self.page.on_close = self._on_close
        self.page.on_disconnect = self._on_disconnect

    def _mark_activity(self, _event: Any = None) -> None:
        self.last_activity = time.monotonic()

    def _scene(self, content: ft.Control, *, key: str, padding: int = 22) -> ft.Container:
        return ft.Container(
            key=key,
            content=content,
            padding=padding,
            gradient=background_gradient(self.palette),
            expand=True,
        )

    def _show(self, content: ft.Control, *, name: str, padding: int = 22) -> None:
        self._current_screen = name
        self._mark_activity()
        self.switcher.content = self._scene(content, key=f"{name}-{time.monotonic_ns()}", padding=padding)
        self.switcher.update()

    def _operation_started(self, name: str) -> bool:
        if name in self._operation_active:
            return False
        self._operation_active.add(name)
        return True

    def _operation_finished(self, name: str) -> None:
        self._operation_active.discard(name)

    def _generation_current(self, generation: int) -> bool:
        return generation == self._session_generation and not self._closing

    def _close_sensitive_dialogs(self) -> None:
        # Clear fields before dismissing the modal stack so a retained control
        # cannot display a secret after locking or closing.
        for field in self._sensitive_fields:
            field.value = ""
        self._sensitive_fields = []
        self._clear_editor_draft()
        try:
            while self.page.pop_dialog() is not None:
                pass
        except (RuntimeError, AttributeError):
            pass

    def _brand(self, *, compact: bool = False) -> ft.Column:
        size = 58 if compact else 72
        return ft.Column(
            [
                brand_mark(size),
                ft.Text(
                    "Cofre Local",
                    size=16 if compact else 20,
                    weight=ft.FontWeight.W_600,
                    color=self.palette.text,
                    font_family="Inter",
                    style=ft.TextStyle(letter_spacing=-0.5),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )

    def _title(self, text: str, subtitle: str) -> ft.Column:
        return ft.Column(
            [
                ft.Text(
                    text,
                    size=26,
                    weight=ft.FontWeight.W_500,
                    color=self.palette.text,
                    font_family="Inter",
                ),
                ft.Text(subtitle, size=13, color=self.palette.muted, font_family="Inter"),
            ],
            spacing=5,
        )

    def _toast(self, message: str, *, error: bool = False) -> None:
        bar = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.ERROR_OUTLINE_ROUNDED if error else ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
                        color="#FFFFFF",
                        size=19,
                    ),
                    ft.Text(message, color="#FFFFFF", size=13, font_family="Inter"),
                ],
                spacing=10,
                tight=True,
            ),
            bgcolor=self.palette.danger if error else "#292929",
            behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=18),
            margin=18,
            padding=ft.Padding.symmetric(horizontal=18, vertical=13),
            duration=3500,
        )
        self.page.show_dialog(bar)

    def show_welcome(self, _event: Any = None) -> None:
        self._session_generation += 1
        recent = Path(str(self.preferences.get("recent_vault", "")))
        recent_exists = bool(str(recent)) and recent.is_file()
        actions: list[ft.Control] = [
            pill_button(
                "Criar novo cofre",
                self.palette,
                self.show_create,
                icon=ft.Icons.ADD_ROUNDED,
                primary=True,
                width=230,
            ),
            pill_button(
                "Abrir cofre",
                self.palette,
                self._pick_vault,
                icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                width=230,
            ),
        ]
        if recent_exists:
            actions.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.HISTORY_ROUNDED, size=17, color=self.palette.muted),
                            ft.Column(
                                [
                                    ft.Text("Abrir o cofre recente", size=12, color=self.palette.text),
                                    ft.Text(
                                        recent.name,
                                        size=10.5,
                                        color=self.palette.muted,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, size=17, color=self.palette.muted),
                        ],
                        spacing=10,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                    bgcolor=self.palette.glass_strong,
                    border=ft.Border.all(1, self.palette.border),
                    border_radius=10,
                    width=230,
                    on_click=lambda _e: self.show_unlock(recent),
                )
            )

        card = glass_card(
            ft.Column(
                [
                    self._brand(),
                    ft.Text(
                        "As suas palavras-passe, apenas suas.",
                        size=23,
                        weight=ft.FontWeight.W_500,
                        color=self.palette.text,
                        text_align=ft.TextAlign.CENTER,
                        font_family="Inter",
                    ),
                    ft.Text(
                        "Cifragem forte, funcionamento offline e um ficheiro que controla.",
                        size=12.5,
                        color=self.palette.muted,
                        text_align=ft.TextAlign.CENTER,
                        font_family="Inter",
                    ),
                    ft.Column(actions, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WIFI_OFF_ROUNDED, size=15, color=self.palette.success),
                            ft.Text("Sem conta · sem cloud", size=11, color=self.palette.muted),
                        ],
                        spacing=7,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=17,
                tight=True,
            ),
            self.palette,
            padding=ft.Padding.symmetric(horizontal=48, vertical=38),
            width=480,
            strong=True,
            elevated=True,
        )
        self._show(
            ft.Container(content=card, alignment=ft.Alignment.CENTER, expand=True),
            name="welcome",
        )

    async def _pick_vault(self, _event: Any = None) -> None:
        selected = await self.file_picker.pick_files(
            dialog_title="Abrir cofre local",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["vault"],
            allow_multiple=False,
        )
        if selected and selected[0].path:
            self.show_unlock(Path(selected[0].path))

    def show_create(self, _event: Any = None) -> None:
        path_field = glass_text_field(
            self.palette,
            label="Localização do cofre",
            value=str(default_vault_path()),
            prefix_icon=ft.Icons.FOLDER_OUTLINED,
        )
        master_field = glass_text_field(
            self.palette,
            label="Palavra-passe mestra",
            password=True,
            prefix_icon=ft.Icons.KEY_ROUNDED,
            autofocus=True,
        )
        confirm_field = glass_text_field(
            self.palette,
            label="Confirmar palavra-passe",
            password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE_ROUNDED,
        )
        self._sensitive_fields.extend([master_field, confirm_field])
        status = ft.Text("", size=11.5, color=self.palette.danger, font_family="Inter")

        async def choose_path(_event: Any) -> None:
            picked = await self.file_picker.save_file(
                dialog_title="Guardar novo cofre",
                file_name="cofre.vault",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["vault"],
            )
            if picked:
                path_field.value = picked if picked.lower().endswith(".vault") else f"{picked}.vault"
                path_field.update()

        async def submit(_event: Any = None) -> None:
            if not self._operation_started("create"):
                return
            self._mark_activity()
            generation = self._session_generation
            try:
                path_text = (path_field.value or "").strip()
                password = master_field.value or ""
                if not path_text:
                    status.value = "Escolha onde guardar o cofre."
                elif len(password) < MIN_MASTER_PASSWORD:
                    status.value = f"Use pelo menos {MIN_MASTER_PASSWORD} caracteres."
                elif password != (confirm_field.value or ""):
                    status.value = "As palavras-passe não coincidem."
                else:
                    status.value = "A criar e a cifrar o cofre…"
                    status.color = self.palette.muted
                    status.update()
                    target = Path(path_text)
                    if target.suffix.lower() != ".vault":
                        target = target.with_suffix(".vault")
                    try:
                        _payload, key, _salt = await asyncio.to_thread(create, target, password)
                        wipe_key(key)
                        opened = await asyncio.to_thread(VaultSession.open, target, password)
                    except FileExistsError:
                        status.value = "Já existe um ficheiro nesse local. Escolha outro nome."
                        status.color = self.palette.danger
                        status.update()
                        return
                    except (VaultError, OSError, ValueError) as exc:
                        status.value = f"Não foi possível criar o cofre: {exc}"
                        status.color = self.palette.danger
                        status.update()
                        return
                    if not self._generation_current(generation):
                        opened.close()
                        return
                    master_field.value = ""
                    confirm_field.value = ""
                    self._open_session(opened)
            finally:
                self._operation_finished("create")

        card = glass_card(
            ft.Column(
                [
                    self._brand(compact=True),
                    self._title("Criar um cofre", "A chave nunca sai deste computador."),
                    ft.Row(
                        [
                            path_field,
                            glass_icon_button(
                                ft.Icons.FOLDER_OPEN_ROUNDED,
                                self.palette,
                                choose_path,
                                tooltip="Escolher local",
                            ),
                        ],
                        spacing=9,
                    ),
                    master_field,
                    confirm_field,
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, size=15, color=self.palette.muted),
                            ft.Text(
                                "Não é possível recuperar uma palavra-passe mestra esquecida.",
                                size=10.5,
                                color=self.palette.muted,
                                expand=True,
                            ),
                        ],
                        spacing=7,
                    ),
                    status,
                    ft.Row(
                        [
                            pill_button("Voltar", self.palette, self.show_welcome),
                            pill_button(
                                "Criar cofre",
                                self.palette,
                                submit,
                                icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                primary=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=10,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=15,
                tight=True,
            ),
            self.palette,
            width=560,
            padding=34,
            strong=True,
            elevated=True,
        )
        self._show(
            ft.Container(content=card, alignment=ft.Alignment.CENTER, expand=True),
            name="create",
        )

    def show_unlock(self, path: Path) -> None:
        self._session_generation += 1
        password_field = glass_text_field(
            self.palette,
            label="Palavra-passe mestra",
            password=True,
            prefix_icon=ft.Icons.KEY_ROUNDED,
            autofocus=True,
        )
        self._sensitive_fields.append(password_field)
        status = ft.Text("", size=11.5, color=self.palette.danger, font_family="Inter")

        async def submit(_event: Any = None) -> None:
            if not self._operation_started("unlock"):
                return
            self._mark_activity()
            generation = self._session_generation
            try:
                password = password_field.value or ""
                if not password:
                    status.value = "Introduza a palavra-passe mestra."
                    status.update()
                    return
                status.value = "A verificar localmente…"
                status.color = self.palette.muted
                status.update()
                try:
                    opened = await asyncio.to_thread(VaultSession.open, path, password)
                except InvalidMasterPassword:
                    status.value = "Palavra-passe incorreta ou ficheiro alterado."
                    status.color = self.palette.danger
                    password_field.value = ""
                    password_field.update()
                    status.update()
                    await password_field.focus()
                    return
                except (InvalidVaultFile, VaultBusyError, OSError, ValueError) as exc:
                    status.value = str(exc)
                    status.color = self.palette.danger
                    status.update()
                    return
                if not self._generation_current(generation):
                    opened.close()
                    return
                password_field.value = ""
                self._open_session(opened)
            finally:
                self._operation_finished("unlock")

        card = glass_card(
            ft.Column(
                [
                    self._brand(compact=True),
                    self._title("Desbloquear cofre", "A desencriptação acontece apenas em memória."),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=18, color=self.palette.accent),
                                ft.Column(
                                    [
                                        ft.Text(path.name, size=12.5, color=self.palette.text),
                                        ft.Text(
                                            str(path.parent),
                                            size=10,
                                            color=self.palette.muted,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                    ],
                                    spacing=1,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=13,
                        bgcolor=self.palette.glass_strong,
                        border=ft.Border.all(1, self.palette.border),
                        border_radius=17,
                    ),
                    password_field,
                    status,
                    ft.Row(
                        [
                            pill_button("Cancelar", self.palette, self.show_welcome),
                            pill_button(
                                "Desbloquear",
                                self.palette,
                                submit,
                                icon=ft.Icons.LOCK_OPEN_ROUNDED,
                                primary=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=10,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=16,
                tight=True,
            ),
            self.palette,
            width=520,
            padding=34,
            strong=True,
            elevated=True,
        )
        self._show(
            ft.Container(content=card, alignment=ft.Alignment.CENTER, expand=True),
            name="unlock",
        )

    def _open_session(self, session: VaultSession) -> None:
        if self.session is not None:
            self.session.close()
        self.session = session
        self._session_generation += 1
        self.preferences["recent_vault"] = str(self.session.path)
        save_preferences(self.preferences)
        self.selected_filter = "Todas"
        self.search_query = ""
        self.selected_id = self.session.entries[0]["id"] if self.session.entries else None
        self.show_dashboard()
        if self.session.path.with_suffix(self.session.path.suffix + ".pending").exists():
            self._show_recovery_dialog(session)

    def _show_recovery_dialog(self, session: VaultSession) -> None:
        def recover(_event: Any) -> None:
            if self.session is not session:
                return
            try:
                session.apply_pending_recovery()
            except (VaultError, OSError) as exc:
                self._toast(f"O rascunho não foi aplicado: {exc}", error=True)
                return
            self.page.pop_dialog()
            self.show_dashboard()
            self._toast("Rascunho cifrado recuperado")

        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title="Rascunho cifrado encontrado",
            content=ft.Text("Uma gravação anterior falhou. O cofre guardado não foi alterado. Pode recuperar este rascunho agora ou mantê-lo para análise.", color=self.palette.muted),
            actions=[pill_button("Manter sem aplicar", self.palette, lambda _e: self.page.pop_dialog()), pill_button("Recuperar", self.palette, recover, primary=True)],
            bgcolor=self.palette.glass_strong,
            shape=ft.RoundedRectangleBorder(radius=24),
        ))

    def _filtered_entries(self) -> list[dict[str, Any]]:
        if self.session is None:
            return []
        query = self.search_query.casefold().strip()
        result: list[dict[str, Any]] = []
        for entry in self.session.entries:
            if self.selected_filter == "Favoritos" and not entry.get("favorite"):
                continue
            if self.selected_filter not in ("Todas", "Favoritos") and entry.get("category") != self.selected_filter:
                continue
            haystack = " ".join(
                str(entry.get(field, "")) for field in ("title", "username", "url", "category", "notes")
            ).casefold()
            if query and query not in haystack:
                continue
            result.append(entry)
        sort_mode = getattr(self, "sort_mode", "Nome")
        if sort_mode == "Recentes":
            return sorted(
                result,
                key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
                reverse=True,
            )
        if sort_mode == "Favoritos":
            return sorted(
                result,
                key=lambda item: (not bool(item.get("favorite")), str(item.get("title", "")).casefold()),
            )
        return sorted(result, key=lambda item: str(item.get("title", "")).casefold())

    def _select_filter(self, value: str) -> None:
        self.selected_filter = value
        self.selected_id = None
        self.show_dashboard()

    def _select_entry(self, entry_id: str) -> None:
        self._mark_activity()
        self.selected_id = entry_id
        self._password_revealed = False
        self._refresh_dashboard_content()

    def _selected_entry(self) -> dict[str, Any] | None:
        if self.session is None or self.selected_id is None:
            return None
        return next((entry for entry in self.session.entries if entry.get("id") == self.selected_id), None)

    def _entry_list_controls(self) -> list[ft.Control]:
        rows: list[ft.Control] = [
            credential_row(
                entry,
                self.palette,
                self.motion,
                selected=entry.get("id") == self.selected_id,
                on_click=lambda _e, entry_id=entry["id"]: self._select_entry(entry_id),
            )
            for entry in self._filtered_entries()
        ]
        if rows:
            return rows
        return [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.SEARCH_OFF_ROUNDED, size=30, color=self.palette.muted),
                        ft.Text("Nenhuma credencial encontrada", size=13, color=self.palette.muted),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                padding=36,
            )
        ]

    def _refresh_dashboard_content(self) -> None:
        entry_list = getattr(self, "_dashboard_entry_list", None)
        detail_host = getattr(self, "_dashboard_detail_host", None)
        if entry_list is None or detail_host is None:
            self.show_dashboard()
            return
        entry_list.controls = self._entry_list_controls()
        selected = self._selected_entry()
        detail_host.content = self._detail_panel(selected) if selected else empty_detail(self.palette)
        result_count = getattr(self, "_dashboard_result_count", None)
        if result_count is not None:
            result_count.value = f"{len(self._filtered_entries())} resultados"
        entry_list.update()
        detail_host.update()
        if result_count is not None:
            result_count.update()

    def show_dashboard(self, _event: Any = None) -> None:
        if self.session is None:
            self.show_welcome()
            return
        selected = self._selected_entry()
        search = glass_text_field(
            self.palette,
            hint="Pesquisar no cofre",
            value=self.search_query,
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            on_change=self._on_search,
            expand=True,
        )
        sort = ft.Dropdown(
            value=self.sort_mode,
            options=[ft.DropdownOption(key=value, text=value) for value in ("Nome", "Recentes", "Favoritos")],
            label="Ordenar",
            width=158,
            text_size=12.5,
            color=self.palette.text,
            filled=True,
            fill_color=self.palette.glass_strong,
            border_color=self.palette.border,
            focused_border_color=self.palette.accent,
            border_radius=10,
            on_select=self._on_sort,
        )
        detail = self._detail_panel(selected) if selected else empty_detail(self.palette)
        self._dashboard_entry_list = ft.Column(
            self._entry_list_controls(),
            spacing=9,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self._dashboard_detail_host = ft.Container(content=detail, expand=4)
        content = ft.Row(
            [
                sidebar(
                    self.palette,
                    self.motion,
                    selected=self.selected_filter,
                    auto_lock_minutes=int(self.preferences["auto_lock_minutes"]),
                    on_select=self._select_filter,
                    on_lock=self.lock,
                    on_settings=self.show_settings,
                ),
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            "O seu cofre",
                                            size=27,
                                            weight=ft.FontWeight.W_500,
                                            color=self.palette.text,
                                            font_family="Inter",
                                        ),
                                        ft.Text(
                                            f"{len(self.session.entries)} credenciais · guardado localmente",
                                            size=11.5,
                                            color=self.palette.muted,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                security_badge(self.palette),
                                pill_button(
                                    "Nova credencial",
                                    self.palette,
                                    self.show_entry_editor,
                                    icon=ft.Icons.ADD_ROUNDED,
                                    primary=True,
                                ),
                            ],
                            spacing=12,
                        ),
                        ft.Row([search, sort], spacing=10),
                        ft.Row(
                            [
                                ft.Text(f"Filtro: {self.selected_filter}", size=11, color=self.palette.accent),
                                self._result_count_control(),
                                pill_button("Limpar filtros", self.palette, lambda _e: self._reset_filters(), icon=ft.Icons.RESTART_ALT_ROUNDED),
                            ],
                            spacing=8,
                        ),
                        ft.Row(
                            [
                                glass_card(
                                    self._dashboard_entry_list,
                                    self.palette,
                                    padding=11,
                                    expand=5,
                                    strong=True,
                                ),
                                self._dashboard_detail_host,
                            ],
                            spacing=14,
                            expand=True,
                        ),
                    ],
                    spacing=14,
                    expand=True,
                ),
            ],
            spacing=18,
            expand=True,
        )
        self._show(content, name="dashboard", padding=18)

    def _on_search(self, event: Any) -> None:
        self._mark_activity()
        self.search_query = event.control.value or ""
        self.selected_id = None
        self._refresh_dashboard_content()

    def _result_count_control(self) -> ft.Text:
        self._dashboard_result_count = ft.Text(
            f"{len(self._filtered_entries())} resultados", size=11.5, color=self.palette.muted
        )
        return self._dashboard_result_count

    def _on_sort(self, event: Any) -> None:
        self._mark_activity()
        self.sort_mode = event.control.value or "Nome"
        self.selected_id = None
        self._refresh_dashboard_content()

    def _reset_filters(self) -> None:
        self.selected_filter = "Todas"
        self.search_query = ""
        self.sort_mode = "Nome"
        self.selected_id = None
        self._password_revealed = False
        self.show_dashboard()

    def _detail_panel(self, entry: dict[str, Any]) -> ft.Container:
        title = str(entry.get("title", "Sem nome"))
        website = str(entry.get("url", ""))
        return glass_card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    title[:1].upper() or "?",
                                    size=24,
                                    weight=ft.FontWeight.W_500,
                                    color=self.palette.text,
                                ),
                                width=58,
                                height=58,
                                alignment=ft.Alignment.CENTER,
                                bgcolor=self.palette.accent_soft,
                                border=ft.Border.all(1, self.palette.border),
                                border_radius=19,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        title,
                                        size=20,
                                        weight=ft.FontWeight.W_500,
                                        color=self.palette.text,
                                        font_family="Inter",
                                    ),
                                    ft.Text(
                                        str(entry.get("category", "Outros")),
                                        size=11,
                                        color=self.palette.accent,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            glass_icon_button(
                                ft.Icons.STAR_ROUNDED
                                if entry.get("favorite")
                                else ft.Icons.STAR_OUTLINE_ROUNDED,
                                self.palette,
                                lambda _e: self._toggle_favorite(entry),
                                tooltip="Favorito",
                                selected=bool(entry.get("favorite")),
                            ),
                        ],
                        spacing=12,
                    ),
                    ft.Divider(height=1, color=self.palette.border),
                    detail_value(
                        "Utilizador",
                        str(entry.get("username", "")),
                        self.palette,
                        on_copy=lambda _e: self._copy_secret(str(entry.get("username", "")), "Utilizador copiado"),
                    ),
                    detail_value(
                        "Palavra-passe",
                        str(entry.get("password", "")),
                        self.palette,
                        secret=True,
                        revealed=self._password_revealed,
                        on_reveal=lambda _e: self._toggle_password_reveal(),
                        on_copy=lambda _e: self._copy_secret(str(entry.get("password", "")), "Palavra-passe copiada"),
                    ),
                    detail_value(
                        "Website",
                        website,
                        self.palette,
                        on_copy=(lambda _e: self._copy_secret(website, "Endereço copiado")) if website else None,
                        on_open=(lambda _e: self._open_website(website)) if website else None,
                    ),
                    detail_value("Notas", str(entry.get("notes", "")), self.palette),
                    ft.Container(expand=True),
                    ft.Row(
                        [
                            pill_button(
                                "Eliminar",
                                self.palette,
                                lambda _e: self._confirm_delete(entry),
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                danger=True,
                            ),
                            pill_button(
                                "Editar",
                                self.palette,
                                lambda _e: self.show_entry_editor(entry),
                                icon=ft.Icons.EDIT_OUTLINED,
                                primary=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    ),
                ],
                spacing=12,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            self.palette,
            padding=20,
            expand=True,
            strong=True,
        )

    def _toggle_password_reveal(self) -> None:
        self._password_revealed = not self._password_revealed
        self._refresh_dashboard_content()

    def _open_website(self, url: str) -> None:
        target = url.strip()
        if target and not target.lower().startswith(("http://", "https://")):
            target = f"https://{target}"
        if target:
            self.page.run_task(self._open_website_async, target)

    async def _open_website_async(self, target: str) -> None:
        await self.page.launch_url(target)

    def _persist(self) -> bool:
        if self.session is None:
            return False
        try:
            self.session.persist()
        except (VaultError, OSError) as exc:
            self._toast(f"Não foi possível guardar: {exc}", error=True)
            return False
        return True

    def _clear_editor_draft(self) -> None:
        """Clear controls that can retain a credential after leaving the editor."""
        for field in self._editor_sensitive_fields:
            field.value = ""
        self._editor_sensitive_fields = []
        self._editor_generation = None

    def _leave_entry_editor(self, _event: Any = None) -> None:
        self._clear_editor_draft()
        if self.session is not None:
            self.show_dashboard()

    def show_entry_editor(self, entry: dict[str, Any] | Any | None = None) -> None:
        """Show a full-page draft bound to the current vault session.

        The draft deliberately has no vault side effects until Guardar.  Both the
        session object and generation are checked at that boundary so an old page
        callback can never write into a subsequently unlocked vault.
        """
        if self.session is None:
            self.show_welcome()
            return
        if not isinstance(entry, dict):
            entry = None
        self._clear_editor_draft()
        session = self.session
        generation = self._session_generation
        entry_id = str(entry.get("id", "")) if entry else None
        self._editor_generation = generation
        title_field = glass_text_field(self.palette, label="Nome da credencial *", hint="Ex.: conta de trabalho", value=str(entry.get("title", "")) if entry else "", autofocus=True)
        username_field = glass_text_field(self.palette, label="Utilizador ou email", value=str(entry.get("username", "")) if entry else "")
        password_field = glass_text_field(
            self.palette,
            label="Palavra-passe",
            value=str(entry.get("password", "")) if entry else "",
            password=True,
            expand=True,
        )
        url_field = glass_text_field(self.palette, label="Website", value=str(entry.get("url", "")) if entry else "")
        notes_field = glass_text_field(
            self.palette,
            label="Notas",
            value=str(entry.get("notes", "")) if entry else "",
            multiline=True,
        )
        self._editor_sensitive_fields = [title_field, username_field, password_field, url_field, notes_field]
        category = ft.Dropdown(
            label="Categoria",
            value=str(entry.get("category", "Outros")) if entry else "Outros",
            options=[ft.DropdownOption(key=value, text=value) for value in CATEGORIES],
            filled=True,
            fill_color=self.palette.glass_strong,
            border_color=self.palette.border,
            focused_border_color=self.palette.accent,
            border_radius=10,
            text_size=13,
            color=self.palette.text,
            expand=True,
        )
        favorite = ft.Checkbox(
            label="Marcar como favorita",
            value=bool(entry.get("favorite")) if entry else False,
            active_color=self.palette.accent,
        )
        status = ft.Text("", size=12, color=self.palette.danger)

        def save_entry(_event: Any) -> None:
            if (
                self.session is not session
                or not self._generation_current(generation)
                or self._editor_generation != generation
            ):
                return
            title = (title_field.value or "").strip()
            if not title:
                status.value = "Dê um nome a esta credencial."
                status.update()
                return
            candidate = session.snapshot()
            if entry_id is None:
                saved = new_entry(
                    title=title,
                    username=username_field.value or "",
                    password=password_field.value or "",
                    url=url_field.value or "",
                    category=category.value or "Outros",
                    notes=notes_field.value or "",
                    favorite=bool(favorite.value),
                )
                candidate["entries"].append(saved)
            else:
                current = next((item for item in candidate["entries"] if item.get("id") == entry_id), None)
                if current is None:
                    status.value = "Esta credencial já não existe. Volte ao cofre."
                    status.update()
                    return
                saved = deepcopy(current)
                saved.update({"title": title, "username": username_field.value or "", "password": password_field.value or "", "url": (url_field.value or "").strip(), "category": category.value or "Outros", "notes": notes_field.value or "", "favorite": bool(favorite.value), "updated_at": utc_now()})
                candidate["entries"] = [saved if item.get("id") == saved["id"] else item for item in candidate["entries"]]
            try:
                session.apply(candidate)
            except (VaultError, OSError) as exc:
                status.value = f"Não foi possível guardar: {exc}"
                status.update()
                return
            else:
                self.selected_id = saved["id"]
                self._clear_editor_draft()
                self.show_dashboard()
                self._toast("Credencial guardada")

        # Only the fields scroll. Header, errors and actions remain visible,
        # including short laptop windows and increased display scaling.
        fields = ft.Column(
            [
                ft.Text("DADOS DE ACESSO", size=11, weight=ft.FontWeight.W_600, color=self.palette.muted),
                ft.ResponsiveRow(
                    [
                        ft.Container(title_field, col={"xs": 12, "md": 6}),
                        ft.Container(username_field, col={"xs": 12, "md": 6}),
                        ft.Container(ft.Row([
                            password_field,
                            glass_icon_button(ft.Icons.AUTO_AWESOME_ROUNDED, self.palette,
                                lambda _e: self._show_password_generator(password_field, generation, session),
                                tooltip="Gerar palavra-passe"),
                        ], spacing=8), col={"xs": 12, "md": 6}),
                        ft.Container(url_field, col={"xs": 12, "md": 6}),
                    ], spacing=16, run_spacing=20,
                ),
                ft.Container(height=4),
                ft.Divider(height=1, color=self.palette.border),
                ft.Text("ORGANIZAÇÃO", size=11, weight=ft.FontWeight.W_600, color=self.palette.muted),
                ft.ResponsiveRow([
                    ft.Container(category, col={"xs": 12, "md": 6}),
                    ft.Container(favorite, col={"xs": 12, "md": 6}, padding=ft.Padding.only(top=8)),
                    ft.Container(notes_field, col=12),
                ], spacing=16, run_spacing=20),
                ft.Text("* Campo obrigatório. Os restantes campos são opcionais.", size=12, color=self.palette.muted),
            ], spacing=18, scroll=ft.ScrollMode.AUTO, expand=True,
        )
        editor_card = glass_card(
            ft.Column([
                ft.Row([
                    glass_icon_button(ft.Icons.ARROW_BACK_ROUNDED, self.palette,
                        self._leave_entry_editor, tooltip="Voltar ao cofre"),
                    ft.Column([
                        ft.Text("Editar credencial" if entry else "Nova credencial", size=24,
                            weight=ft.FontWeight.W_600, color=self.palette.text),
                        ft.Text("Um acesso seguro, num só lugar.", size=13, color=self.palette.muted),
                    ], spacing=4, expand=True),
                    brand_mark(38),
                ], spacing=16),
                ft.Divider(height=1, color=self.palette.border),
                ft.Container(fields, expand=True, padding=ft.Padding.symmetric(vertical=8)),
                ft.Divider(height=1, color=self.palette.border),
                status,
                ft.Row([
                    ft.Icon(ft.Icons.LOCK_OUTLINE_ROUNDED, size=16, color=self.palette.muted),
                    ft.Text("Guardado apenas neste dispositivo.", size=12,
                        color=self.palette.muted, expand=True),
                    pill_button("Cancelar", self.palette, self._leave_entry_editor),
                    pill_button("Guardar", self.palette, save_entry,
                        icon=ft.Icons.CHECK_ROUNDED, primary=True),
                ], spacing=12),
            ], spacing=16, expand=True),
            self.palette, padding=24, strong=True, expand=True,
        )
        self._show(editor_card, name="entry-editor", padding=18)

    # Compatibility for callbacks created by earlier dashboard instances.
    def _show_entry_dialog(self, entry: dict[str, Any] | Any | None = None) -> None:
        self.show_entry_editor(entry)

    def _show_password_generator(
        self,
        target_field: ft.TextField,
        generation: int | None = None,
        origin_session: VaultSession | None = None,
    ) -> None:
        length_label = ft.Text("24 caracteres", size=12.5, color=self.palette.text)
        length = ft.Slider(
            value=24,
            min=8,
            max=64,
            divisions=56,
            active_color=self.palette.accent,
            inactive_color=self.palette.accent_soft,
        )
        uppercase = ft.Checkbox(label="Maiúsculas", value=True, active_color=self.palette.accent)
        lowercase = ft.Checkbox(label="Minúsculas", value=True, active_color=self.palette.accent)
        digits = ft.Checkbox(label="Números", value=True, active_color=self.palette.accent)
        symbols = ft.Checkbox(label="Símbolos", value=True, active_color=self.palette.accent)
        generated = glass_text_field(
            self.palette,
            label="Resultado",
            value=generate_password(),
            password=True,
        )
        self._sensitive_fields.append(generated)
        status = ft.Text("", size=12, color=self.palette.danger, live_region=True)

        def regenerate(_event: Any = None) -> None:
            try:
                generated.value = generate_password(
                    int(length.value or 24),
                    uppercase=bool(uppercase.value),
                    lowercase=bool(lowercase.value),
                    digits=bool(digits.value),
                    symbols=bool(symbols.value),
                )
            except ValueError as exc:
                status.value = str(exc)
                status.update()
                return
            status.value = ""
            generated.update()
            status.update()

        def update_length(_event: Any) -> None:
            length_label.value = f"{int(length.value or 24)} caracteres"
            length_label.update()
            regenerate()

        length.on_change = update_length

        def use_password(_event: Any) -> None:
            if generation is not None and (
                not self._generation_current(generation)
                or self._editor_generation != generation
                or (origin_session is not None and self.session is not origin_session)
            ):
                self.page.pop_dialog()
                return
            value = generated.value or ""
            if not value:
                regenerate()
                value = generated.value or ""
            if value:
                target_field.value = value
                target_field.update()
                generated.value = ""
                self.page.pop_dialog()
                self._toast("Palavra-passe segura aplicada")

        def cancel(_event: Any) -> None:
            generated.value = ""
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title="Gerar palavra-passe",
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Gerada localmente com aleatoriedade criptográfica.",
                            size=11.5,
                            color=self.palette.muted,
                        ),
                        length_label,
                        length,
                        ft.Row([uppercase, lowercase], spacing=12),
                        ft.Row([digits, symbols], spacing=12),
                        generated,
                        status,
                    ],
                    spacing=10,
                    tight=True,
                ),
                width=460,
            ),
            actions=[
                pill_button("Cancelar", self.palette, cancel),
                pill_button("Gerar outra", self.palette, regenerate, icon=ft.Icons.REFRESH_ROUNDED),
                pill_button("Usar esta", self.palette, use_password, icon=ft.Icons.CHECK_ROUNDED, primary=True),
            ],
            bgcolor=self.palette.glass_strong,
            barrier_color=ft.Colors.with_opacity(0.32, "#000000"),
            shape=ft.RoundedRectangleBorder(radius=24),
        )
        self.page.show_dialog(dialog)

    def _toggle_favorite(self, entry: dict[str, Any]) -> None:
        if self.session is None:
            return
        session = self.session
        generation = self._session_generation
        entry_id = entry.get("id")
        if not self._generation_current(generation) or self.session is not session:
            return
        candidate = session.snapshot()
        found = False
        for item in candidate["entries"]:
            if item.get("id") == entry_id:
                item["favorite"] = not bool(item.get("favorite"))
                item["updated_at"] = utc_now()
                found = True
        if not found or self.session is not session or not self._generation_current(generation):
            return
        try:
            session.apply(candidate)
        except (VaultError, OSError) as exc:
            self._toast(f"Não foi possível guardar: {exc}", error=True)
        else:
            self.show_dashboard()

    def _confirm_delete(self, entry: dict[str, Any]) -> None:
        if self.session is None:
            return
        session = self.session
        generation = self._session_generation
        entry_id = entry.get("id")

        def remove(_event: Any) -> None:
            if self.session is not session or not self._generation_current(generation):
                return
            candidate = session.snapshot()
            remaining = [item for item in candidate["entries"] if item.get("id") != entry_id]
            if len(remaining) == len(candidate["entries"]):
                self.page.pop_dialog()
                return
            candidate["entries"] = remaining
            try:
                session.apply(candidate)
            except (VaultError, OSError) as exc:
                self._toast(f"Não foi possível guardar: {exc}", error=True)
            else:
                self.selected_id = None
                self.page.pop_dialog()
                self.show_dashboard()
                self._toast("Credencial eliminada")

        dialog = ft.AlertDialog(
            modal=True,
            title="Eliminar credencial?",
            content=ft.Text(
                f"\u201c{entry.get('title', 'Sem nome')}\u201d será removida do cofre cifrado.",
                color=self.palette.muted,
            ),
            actions=[
                pill_button("Cancelar", self.palette, lambda _e: self.page.pop_dialog()),
                pill_button("Eliminar", self.palette, remove, danger=True),
            ],
            bgcolor=self.palette.glass_strong,
            shape=ft.RoundedRectangleBorder(radius=24),
        )
        self.page.show_dialog(dialog)

    def _copy_secret(self, value: str, message: str) -> None:
        if not value or self.session is None:
            return
        self.page.run_task(self._copy_secret_async, value, message, self._session_generation, self.session)

    async def _copy_secret_async(
        self, value: str, message: str, generation: int, origin_session: VaultSession
    ) -> None:
        if not self._generation_current(generation) or self.session is not origin_session:
            return
        await self.clipboard.set(value)
        if not self._generation_current(generation) or self.session is not origin_session:
            # A lock happened while the clipboard service was awaiting; do not
            # leave a copied secret behind.
            await self._clear_clipboard_now()
            return
        self._clipboard_token += 1
        token = self._clipboard_token
        self.page.run_task(self._clear_clipboard_later, value, token)
        self._toast(f"{message} · limpa em 30 s")

    async def _clear_clipboard_later(self, value: str, token: int) -> None:
        await asyncio.sleep(30)
        if token != self._clipboard_token:
            return
        try:
            if await self.clipboard.get() == value:
                await self.clipboard.set("")
        except Exception:
            pass

    def show_settings(self, _event: Any = None) -> None:
        if self.session is None:
            self.show_welcome()
            return
        auto_lock = ft.Slider(
            value=int(self.preferences["auto_lock_minutes"]),
            min=1,
            max=60,
            divisions=59,
            label="{value} min",
            active_color=self.palette.accent,
            inactive_color=self.palette.accent_soft,
        )
        theme_cards: list[ft.Control] = []
        for key, palette in PALETTES.items():
            selected = key == self.palette.key
            theme_cards.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(width=22, height=22, bgcolor=palette.background, border_radius=11),
                                    ft.Container(width=22, height=22, bgcolor=palette.accent, border_radius=11),
                                    ft.Icon(
                                        ft.Icons.CHECK_CIRCLE_ROUNDED if selected else ft.Icons.CIRCLE_OUTLINED,
                                        size=19,
                                        color=self.palette.accent if selected else self.palette.muted,
                                    ),
                                ],
                                spacing=7,
                            ),
                            ft.Text(palette.name, size=12.5, color=self.palette.text, weight=ft.FontWeight.W_500),
                        ],
                        spacing=9,
                    ),
                    padding=14,
                    width=132,
                    bgcolor=self.palette.accent_soft if selected else self.palette.glass_strong,
                    border=ft.Border.all(1.4 if selected else 1, self.palette.accent if selected else self.palette.border),
                    border_radius=19,
                    on_click=lambda _e, theme_key=key: self._apply_theme(theme_key),
                    animate=self.motion.quick(),
                )
            )

        def save_lock(_event: Any) -> None:
            self.preferences["auto_lock_minutes"] = int(auto_lock.value or 5)
            save_preferences(self.preferences)
            self.last_activity = time.monotonic()
            self._toast("Bloqueio automático atualizado")
            self.show_settings()

        card = glass_card(
            ft.Column(
                [
                    ft.Row(
                        [
                            self._title("Definições", "Personalização local, sem criar uma conta."),
                            ft.Container(expand=True),
                            pill_button("Voltar ao cofre", self.palette, self.show_dashboard, icon=ft.Icons.ARROW_BACK_ROUNDED),
                        ],
                        spacing=12,
                    ),
                    ft.Divider(color=self.palette.border),
                    ft.Text(
                        "APARÊNCIA",
                        size=10.5,
                        color=self.palette.muted,
                        weight=ft.FontWeight.W_600,
                        style=ft.TextStyle(letter_spacing=1.5),
                    ),
                    ft.Text("Tema", size=16, color=self.palette.text, weight=ft.FontWeight.W_500),
                    ft.Row(theme_cards, spacing=10, wrap=True),
                    ft.Divider(color=self.palette.border),
                    ft.Text(
                        "SEGURANÇA",
                        size=10.5,
                        color=self.palette.muted,
                        weight=ft.FontWeight.W_600,
                        style=ft.TextStyle(letter_spacing=1.5),
                    ),
                    ft.Text("Bloqueio automático", size=16, color=self.palette.text, weight=ft.FontWeight.W_500),
                    ft.Text(
                        "O cofre fecha quando não houver atividade. As animações seguem automaticamente a preferência do Windows.",
                        size=11.5,
                        color=self.palette.muted,
                    ),
                    auto_lock,
                    ft.Row(
                        [
                            pill_button("Guardar tempo", self.palette, save_lock, icon=ft.Icons.SCHEDULE_ROUNDED),
                            pill_button(
                                "Alterar palavra-passe mestra",
                                self.palette,
                                self._change_master_dialog,
                                icon=ft.Icons.KEY_ROUNDED,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Divider(color=self.palette.border),
                    ft.Text(
                        "FICHEIRO",
                        size=10.5,
                        color=self.palette.muted,
                        weight=ft.FontWeight.W_600,
                        style=ft.TextStyle(letter_spacing=1.5),
                    ),
                    ft.Text(str(self.session.path), size=11, color=self.palette.muted, selectable=True),
                    ft.Row(
                        [
                            pill_button(
                                "Exportar cópia cifrada",
                                self.palette,
                                self._export_copy,
                                icon=ft.Icons.SAVE_ALT_ROUNDED,
                            ),
                            pill_button(
                                "Bloquear agora",
                                self.palette,
                                self.lock,
                                icon=ft.Icons.LOCK_OUTLINE_ROUNDED,
                                primary=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Divider(color=self.palette.border),
                    ft.Text("SOBRE", size=10.5, color=self.palette.muted, weight=ft.FontWeight.W_600, style=ft.TextStyle(letter_spacing=1.5)),
                    ft.Text(f"Cofre Local · versão {__version__}", size=11.5, color=self.palette.muted),
                    ft.Text(
                        "Gestor offline. A licença da aplicação está por definir.",
                        size=11.5,
                        color=self.palette.muted,
                    ),
                ],
                spacing=13,
                scroll=ft.ScrollMode.AUTO,
            ),
            self.palette,
            padding=30,
            strong=True,
            elevated=True,
            width=820,
        )
        self._show(ft.Row([card], alignment=ft.MainAxisAlignment.CENTER), name="settings")

    def _apply_theme(self, key: str) -> None:
        if key not in PALETTES or key == self.palette.key:
            return
        self.preferences["theme"] = key
        save_preferences(self.preferences)
        self.palette = get_palette(key)
        self.page.theme = page_theme(self.palette)
        self.page.theme_mode = ft.ThemeMode.DARK if self.palette.dark else ft.ThemeMode.LIGHT
        self.page.views[0].bgcolor = self.palette.background
        self.page.update()
        self.show_settings()

    async def _export_copy(self, _event: Any = None) -> None:
        if self.session is None:
            return
        session = self.session
        generation = getattr(self, "_session_generation", 0)
        destination = await self.file_picker.save_file(
            dialog_title="Exportar cópia cifrada",
            file_name=f"{session.path.stem}-copia.vault",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["vault"],
        )
        if not destination:
            return
        if (hasattr(self, "_session_generation") and not self._generation_current(generation)) or self.session is not session:
            return
        target = Path(destination)
        if target.suffix.lower() != ".vault":
            target = target.with_suffix(".vault")
        try:
            export_encrypted_copy(session.path, target)
        except (OSError, ValueError) as exc:
            self._toast(str(exc), error=True)
            return
        self._toast("Cópia cifrada exportada")

    def _change_master_dialog(self, _event: Any = None) -> None:
        if self.session is None:
            return
        new_password = glass_text_field(self.palette, label="Nova palavra-passe mestra", password=True, autofocus=True)
        confirm = glass_text_field(self.palette, label="Confirmar nova palavra-passe", password=True)
        self._sensitive_fields.extend([new_password, confirm])
        status = ft.Text("", size=12, color=self.palette.danger, live_region=True)

        async def change(_event: Any) -> None:
            if self.session is None or not self._operation_started("rotate"):
                return
            session = self.session
            generation = self._session_generation
            try:
                value = new_password.value or ""
                if len(value) < MIN_MASTER_PASSWORD:
                    status.value = f"Use pelo menos {MIN_MASTER_PASSWORD} caracteres."
                    status.update()
                    return
                if value != (confirm.value or ""):
                    status.value = "As palavras-passe não coincidem."
                    status.update()
                    return
                status.value = "A voltar a cifrar o cofre…"
                status.color = self.palette.muted
                status.update()
                try:
                    await asyncio.to_thread(session.rotate_master_password, value)
                except (VaultError, OSError, ValueError) as exc:
                    status.value = f"Não foi possível alterar: {exc}"
                    status.color = self.palette.danger
                    status.update()
                    return
                if not self._generation_current(generation) or self.session is not session:
                    return
                new_password.value = ""
                confirm.value = ""
                self.page.pop_dialog()
                self._toast("Palavra-passe mestra alterada")
            finally:
                self._operation_finished("rotate")

        dialog = ft.AlertDialog(
            modal=True,
            title="Alterar palavra-passe mestra",
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Será criada automaticamente uma cópia .backup antes da alteração.",
                            size=11.5,
                            color=self.palette.muted,
                        ),
                        new_password,
                        confirm,
                        status,
                    ],
                    spacing=12,
                ),
                width=460,
            ),
            actions=[
                pill_button("Cancelar", self.palette, lambda _e: self.page.pop_dialog()),
                pill_button("Alterar", self.palette, change, icon=ft.Icons.KEY_ROUNDED, primary=True),
            ],
            bgcolor=self.palette.glass_strong,
            shape=ft.RoundedRectangleBorder(radius=24),
        )
        self.page.show_dialog(dialog)

    def lock(self, _event: Any = None) -> None:
        if self.session is None:
            self.show_welcome()
            return
        path = self.session.path
        session = self._detach_session_for_lock()
        self.show_unlock(path)
        if session is not None:
            self.page.run_task(self._finish_secure_close, session)

    def _detach_session_for_lock(self, *, page_services_available: bool = True) -> VaultSession | None:
        if self.session is None:
            return None
        session = self.session
        self._session_generation += 1
        if page_services_available:
            self._close_sensitive_dialogs()
        else:
            # A disconnect has no live Flet connection. Do not call pop_dialog,
            # update, clipboard, or run_task there; just drop local references.
            for field in self._sensitive_fields:
                field.value = ""
            self._sensitive_fields = []
            self._clear_editor_draft()
        self.session = None
        self.selected_id = None
        self.search_query = ""
        self._password_revealed = False
        # These controls retain rendered credential values and callbacks. Clear
        # their children before dropping the cached references; this does not
        # require a page update, so it is also safe after a disconnect.
        entry_list = getattr(self, "_dashboard_entry_list", None)
        if entry_list is not None:
            entry_list.controls = []
        detail_host = getattr(self, "_dashboard_detail_host", None)
        if detail_host is not None:
            detail_host.content = None
        self._dashboard_entry_list = None
        self._dashboard_detail_host = None
        self._dashboard_result_count = None
        self._clipboard_token += 1
        self._detached_closes[id(session)] = session
        self._detached_close_event.clear()
        if page_services_available:
            self.page.run_task(self._clear_clipboard_now)
        else:
            switcher = getattr(self, "switcher", None)
            if switcher is not None:
                switcher.content = ft.Container(expand=True)
        return session

    async def _finish_secure_close(self, session: VaultSession) -> None:
        close_id = id(session)
        if close_id in self._finishing_close_ids:
            return
        self._finishing_close_ids.add(close_id)
        try:
            notice = await asyncio.to_thread(session.secure_close)
            if notice and not self._closing:
                self._toast(notice, error=True)
        finally:
            self._finishing_close_ids.discard(close_id)
            self._detached_closes.pop(close_id, None)
            if not self._detached_closes:
                self._detached_close_event.set()

    async def _await_detached_closes(self) -> None:
        if self._detached_closes:
            await self._detached_close_event.wait()

    async def _clear_clipboard_now(self) -> None:
        try:
            await self.clipboard.set("")
        except Exception:
            pass

    async def _security_loop(self) -> None:
        while not self._closing:
            await asyncio.sleep(1)
            if self.session is None:
                continue
            minutes = int(self.preferences.get("auto_lock_minutes", 5))
            if time.monotonic() - self.last_activity >= minutes * 60:
                self.lock()

    async def _close_after_smoke_test(self) -> None:
        await asyncio.sleep(1.2)
        try:
            await self.page.window.close()
        except RuntimeError:
            # O cliente oculto pode encerrar a sessão antes da callback de teste.
            pass

    def _on_close(self, _event: Any = None) -> None:
        self._closing = True
        session = self._detach_session_for_lock(page_services_available=False)
        if session is not None:
            self._schedule_disconnected_close(session)

    def _on_disconnect(self, _event: Any = None) -> None:
        self._on_close()

    def _schedule_disconnected_close(self, session: VaultSession) -> None:
        """Close a detached vault after Flet has lost its page connection."""
        try:
            asyncio.create_task(self._finish_secure_close(session))
        except RuntimeError:
            # Defensive fallback for a client that invokes the callback after
            # its event loop has already stopped.
            try:
                session.secure_close()
            finally:
                self._detached_closes.pop(id(session), None)
                if not self._detached_closes:
                    self._detached_close_event.set()

    def _on_window_event(self, event: Any) -> None:
        if getattr(event, "type", None) == ft.WindowEventType.CLOSE:
            self.page.run_task(self._close_window_async)

    async def _close_window_async(self) -> None:
        self._closing = True
        session = self._detach_session_for_lock()
        if session is not None:
            await self._finish_secure_close(session)
        await self._await_detached_closes()
        await self._clear_clipboard_now()
        await self.page.window.destroy()


def main(page: ft.Page) -> None:
    CofreLocalFletApp(page)


def run() -> None:
    view = ft.AppView.FLET_APP_HIDDEN if os.environ.get("COFRE_LOCAL_FLET_SMOKE") == "1" else ft.AppView.FLET_APP
    ft.run(main, view=view, assets_dir="assets")
