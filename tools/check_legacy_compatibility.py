"""Inspect legacy application code and check compatibility using synthetic data."""
import sys
import tempfile
import types
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PyInstaller.archive.readers import CArchiveReader
from cofre_local.vault import VaultSession

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('executable', type=Path, help='Caminho do executável antigo a verificar')
args = parser.parse_args()
archive = CArchiveReader(str(args.executable)).open_embedded_archive('PYZ.pyz')
code = archive.extract('cofre_local.app')
todo = [code]
while todo:
    item = todo.pop()
    todo.extend(x for x in item.co_consts if isinstance(x, types.CodeType))
    if any(name in item.co_name for name in ('save', 'entry')):
        print(item.co_name, item.co_names,
              [x for x in item.co_consts if isinstance(x, (str, tuple)) and len(str(x)) < 600], flush=True)

legacy = types.ModuleType('cofre_legacy_compatibility_test')
sys.modules[legacy.__name__] = legacy
exec(archive.extract('cofre_local.vault'), legacy.__dict__)
print('LEGACY_MODULE_LOADED', flush=True)
with tempfile.TemporaryDirectory(prefix='cofre-compatibility-') as temporary:
    path = Path(temporary) / 'synthetic.vault'
    _, key, _ = legacy.create(path, 'synthetic compatibility check only')
    legacy.wipe_key(key)
    before = path.read_bytes()
    opened = VaultSession.open(path, 'synthetic compatibility check only')
    print('LEGACY_EMPTY_VAULT_OPEN=PASS FILE_UNCHANGED=', path.read_bytes() == before, flush=True)
    opened.close()
