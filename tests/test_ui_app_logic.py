from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cofre_local.ui_flet.app import CofreLocalFletApp, default_vault_path


class DashboardLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = CofreLocalFletApp.__new__(CofreLocalFletApp)
        self.app.session = SimpleNamespace(
            entries=[
                {
                    "id": "2",
                    "title": "Banco",
                    "username": "rui",
                    "password": "segredo-que-nao-deve-ser-pesquisavel",
                    "url": "banco.example",
                    "category": "Finanças",
                    "notes": "conta principal",
                    "favorite": True,
                },
                {
                    "id": "1",
                    "title": "Apple",
                    "username": "mail@example.com",
                    "password": "outro-segredo",
                    "url": "apple.example",
                    "category": "Pessoal",
                    "notes": "",
                    "favorite": False,
                },
            ]
        )
        self.app.selected_filter = "Todas"
        self.app.search_query = ""
        self.app.selected_id = None

    def test_entries_are_sorted_without_mutating_vault_order(self) -> None:
        result = self.app._filtered_entries()
        self.assertEqual([entry["title"] for entry in result], ["Apple", "Banco"])
        self.assertEqual([entry["title"] for entry in self.app.session.entries], ["Banco", "Apple"])

    def test_category_and_favorite_filters(self) -> None:
        self.app.selected_filter = "Finanças"
        self.assertEqual([entry["id"] for entry in self.app._filtered_entries()], ["2"])
        self.app.selected_filter = "Favoritos"
        self.assertEqual([entry["id"] for entry in self.app._filtered_entries()], ["2"])

    def test_search_uses_metadata_but_never_password_contents(self) -> None:
        self.app.search_query = "principal"
        self.assertEqual([entry["id"] for entry in self.app._filtered_entries()], ["2"])
        self.app.search_query = "segredo-que-nao-deve-ser-pesquisavel"
        self.assertEqual(self.app._filtered_entries(), [])

    def test_selected_entry_is_resolved_by_id(self) -> None:
        self.app.selected_id = "1"
        self.assertEqual(self.app._selected_entry()["title"], "Apple")

    def test_default_vault_path_uses_vault_extension(self) -> None:
        self.assertEqual(default_vault_path().suffix, ".vault")


class AsyncServiceTests(unittest.TestCase):
    def test_open_vault_awaits_file_picker_before_indexing_result(self) -> None:
        class Picker:
            async def pick_files(self, **_kwargs):
                return [SimpleNamespace(path=r"C:\Dados\meu-cofre.vault")]

        app = CofreLocalFletApp.__new__(CofreLocalFletApp)
        app.file_picker = Picker()
        opened: list[Path] = []
        app.show_unlock = opened.append

        asyncio.run(app._pick_vault())

        self.assertEqual(opened, [Path(r"C:\Dados\meu-cofre.vault")])

    def test_export_awaits_save_picker_and_copies_encrypted_file(self) -> None:
        class Picker:
            def __init__(self, destination: Path) -> None:
                self.destination = destination

            async def save_file(self, **_kwargs):
                return str(self.destination)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "origem.vault"
            destination = root / "copia.vault"
            source.write_bytes(b"encrypted-envelope")

            app = CofreLocalFletApp.__new__(CofreLocalFletApp)
            app.session = SimpleNamespace(path=source)
            app.file_picker = Picker(destination)
            messages: list[tuple[str, bool]] = []
            app._toast = lambda message, error=False: messages.append((message, error))

            asyncio.run(app._export_copy())

            self.assertEqual(destination.read_bytes(), b"encrypted-envelope")
            self.assertEqual(messages, [("Cópia cifrada exportada", False)])


if __name__ == "__main__":
    unittest.main()
