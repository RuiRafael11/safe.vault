from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
from cofre_local.ui_flet.app import CofreLocalFletApp


class SecurityLifecycleTests(unittest.TestCase):
    def make_app(self):
        app = CofreLocalFletApp.__new__(CofreLocalFletApp)
        app._session_generation = 2
        app._closing = False
        app._clipboard_token = 0
        app._operation_active = set()
        app._password_revealed = True
        app._sensitive_fields = []
        app._editor_sensitive_fields = []
        app._editor_generation = None
        app._detached_closes = {}
        app._finishing_close_ids = set()
        app._detached_close_event = asyncio.Event()
        app._closing_sessions = []
        app.session = Mock()
        app.selected_id = 'synthetic'
        app.search_query = 'synthetic search'
        app.page = SimpleNamespace(pop_dialog=Mock(return_value=None), run_task=Mock())
        app.clipboard = SimpleNamespace(set=AsyncMock(), get=AsyncMock(return_value=''))
        app._toast = Mock()
        return app

    def test_stale_clipboard_callback_never_writes_secret(self):
        app = self.make_app()
        asyncio.run(app._copy_secret_async('synthetic secret', 'copied', 1, app.session))
        app.clipboard.set.assert_not_awaited()

    def test_lock_during_clipboard_write_clears_secret(self):
        app = self.make_app()
        async def copy(value):
            if value:
                app._session_generation += 1
        app.clipboard.set.side_effect = copy
        asyncio.run(app._copy_secret_async('synthetic secret', 'copied', 2, app.session))
        self.assertEqual(app.clipboard.set.await_args_list[-1].args, ('',))
        app._toast.assert_not_called()

    def test_lock_detaches_session_and_closes_entire_dialog_stack(self):
        app = self.make_app()
        app.page.pop_dialog.side_effect = [SimpleNamespace(), SimpleNamespace(), None]
        app._dashboard_entry_list = SimpleNamespace(controls=["credential control"])
        app._dashboard_detail_host = SimpleNamespace(content="credential detail")
        app._dashboard_result_count = SimpleNamespace(value="1 resultado")
        session = app.session
        self.assertIs(app._detach_session_for_lock(), session)
        self.assertIsNone(app.session)
        self.assertGreater(app._session_generation, 2)
        self.assertEqual(app.search_query, '')
        self.assertFalse(app._password_revealed)
        self.assertEqual(app.page.pop_dialog.call_count, 3)
        self.assertEqual(app._dashboard_entry_list, None)
        self.assertEqual(app._dashboard_detail_host, None)
        self.assertEqual(app._dashboard_result_count, None)

    def test_disconnected_detach_drops_the_old_screen_without_page_services(self):
        app = self.make_app()
        app._dashboard_entry_list = SimpleNamespace(controls=["credential control"])
        app._dashboard_detail_host = SimpleNamespace(content="credential detail")
        app.switcher = SimpleNamespace(content="dashboard")

        app._detach_session_for_lock(page_services_available=False)

        self.assertEqual(app._dashboard_entry_list, None)
        self.assertEqual(app._dashboard_detail_host, None)
        self.assertIsInstance(app.switcher.content, ft.Container)
        app.page.run_task.assert_not_called()

    def test_native_close_event_dispatches_cleanup(self):
        app = self.make_app()
        app._on_window_event(SimpleNamespace(type=ft.WindowEventType.CLOSE))
        app.page.run_task.assert_called_once_with(app._close_window_async)

    def test_duplicate_sensitive_operation_is_rejected(self):
        app = self.make_app()
        self.assertTrue(app._operation_started('rotate'))
        self.assertFalse(app._operation_started('rotate'))
        app._operation_finished('rotate')
        self.assertTrue(app._operation_started('rotate'))


if __name__ == '__main__':
    unittest.main()
