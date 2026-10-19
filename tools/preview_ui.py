"""Isolated browser QA with synthetic data; never opens the owner's vault."""
import sys
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import flet as ft
import cofre_local.ui_flet.app as ui
from cofre_local.vault import create, wipe_key, VaultSession, new_entry

ui.load_preferences = lambda: dict(theme='midnight', recent_vault='', auto_lock_minutes=60)
ui.save_preferences = lambda *_args: None


def main(page):
    app = ui.CofreLocalFletApp(page)
    temporary = tempfile.TemporaryDirectory(prefix='cofre-design-qa-')
    app._qa_temporary = temporary
    path = Path(temporary.name) / 'demo.vault'
    _, key, _ = create(path, 'synthetic design review only')
    wipe_key(key)
    session = VaultSession.open(path, 'synthetic design review only')
    draft = session.snapshot()
    for title, user, category in [('GitHub', 'demo@example.com', 'Trabalho'),
                                  ('Proton Mail', 'demo@example.com', 'Pessoal'),
                                  ('Banco', 'conta de exemplo', 'Finanças')]:
        draft['entries'].append(new_entry(title=title, username=user,
            password='synthetic-example', category=category))
    session.apply(draft)
    app._open_session(session)


os.environ['FLET_FORCE_WEB_SERVER'] = 'true'
ft.run(main, view=None, port=8766, no_cdn=True,
       assets_dir=str(Path(__file__).resolve().parents[1] / 'assets'))
