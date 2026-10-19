"""Independent reviewer checks using only synthetic temporary vaults."""
import tempfile
import unittest
import threading
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from cofre_local import vault as v

PASSWORD = 'synthetic review passphrase 2026'


class StorageReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'review.vault'
        _, key, _ = v.create(self.path, PASSWORD)
        v.wipe_key(key)
        self.session = v.VaultSession.open(self.path, PASSWORD)
        self.addCleanup(self.session.close)

    def test_second_session_rejected_until_first_closed(self):
        with self.assertRaises(v.VaultBusyError):
            v.VaultSession.open(self.path, PASSWORD)
        self.session.close()
        reopened = v.VaultSession.open(self.path, PASSWORD)
        reopened.close()

    def test_external_change_is_never_replaced(self):
        altered = self.path.read_bytes() + b' '
        self.path.write_bytes(altered)
        candidate = self.session.snapshot()
        candidate['entries'].append(v.new_entry(title='unsaved', password='fictitious'))
        with self.assertRaises(v.VaultChangedError):
            self.session.apply(candidate)
        self.assertEqual(self.path.read_bytes(), altered)
        self.assertEqual(self.session.entries, [])

    def test_failed_transaction_rolls_back_without_dirty_original(self):
        before = self.path.read_bytes()
        candidate = self.session.snapshot()
        candidate['entries'].append(v.new_entry(title='failed', password='fictitious'))
        with patch.object(v, '_atomic_write', side_effect=OSError('simulated full disk')):
            with self.assertRaises(OSError):
                self.session.apply(candidate)
        self.assertEqual(self.session.entries, [])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.session.dirty)
        self.session.apply(candidate)
        self.assertEqual(len(self.session.entries), 1)

    def test_commit_does_not_depend_on_post_write_read(self):
        candidate = self.session.snapshot()
        candidate['entries'].append(v.new_entry(title='committed'))
        original = v.fingerprint
        calls = []
        def guarded(path):
            calls.append(path)
            if len(calls) > 1:
                raise OSError('simulated read failure after replace')
            return original(path)
        with patch.object(v, 'fingerprint', side_effect=guarded):
            self.session.apply(candidate)
        self.assertEqual(len(self.session.entries), 1)
        payload, key, _ = v.unlock(self.path, PASSWORD)
        v.wipe_key(key)
        self.assertEqual(payload['entries'][0]['title'], 'committed')

    def test_password_rotation_preserves_old_backup_and_new_vault(self):
        self.session.rotate_master_password('different synthetic passphrase 2026')
        payload, key, _ = v.unlock(self.path, 'different synthetic passphrase 2026')
        v.wipe_key(key)
        backup, key, _ = v.unlock(self.path.with_suffix('.vault.backup'), PASSWORD)
        v.wipe_key(key)
        self.assertEqual(payload['vault_id'], backup['vault_id'])
        with self.assertRaises(v.InvalidMasterPassword):
            v.unlock(self.path, PASSWORD)

    def test_closed_session_cannot_commit_old_draft(self):
        candidate = self.session.snapshot()
        candidate['entries'].append(v.new_entry(title='stale draft'))
        before = self.path.read_bytes()
        self.session.close()
        with self.assertRaises(v.VaultError):
            self.session.apply(candidate)
        self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_draft_cannot_overwrite_newer_saved_entry(self):
        first, stale = self.session.snapshot(), self.session.snapshot()
        first['entries'].append(v.new_entry(title='first'))
        stale['entries'].append(v.new_entry(title='stale'))
        self.session.apply(first)
        with self.assertRaises(v.VaultChangedError):
            self.session.apply(stale)
        self.assertEqual([x['title'] for x in self.session.entries], ['first'])

    def test_export_cannot_overwrite_another_open_vault(self):
        target = self.path.parent / 'second.vault'
        _, key, _ = v.create(target, PASSWORD)
        v.wipe_key(key)
        other = v.VaultSession.open(target, PASSWORD)
        self.addCleanup(other.close)
        before = target.read_bytes()
        with self.assertRaises(v.VaultBusyError):
            v.export_encrypted_copy(self.path, target)
        self.assertEqual(target.read_bytes(), before)

    def test_failed_backup_write_preserves_previous_backup_and_vault(self):
        first = self.session.snapshot()
        first['entries'].append(v.new_entry(title='first'))
        self.session.apply(first)
        backup_path = self.path.with_suffix('.vault.backup')
        before, backup = self.path.read_bytes(), backup_path.read_bytes()
        candidate = self.session.snapshot()
        candidate['entries'].append(v.new_entry(title='second'))
        original_replace = v.os.replace
        def fail_backup(source, destination):
            if Path(destination) == backup_path:
                raise OSError('simulated backup replacement failure')
            return original_replace(source, destination)
        with patch.object(v.os, 'replace', side_effect=fail_backup):
            with self.assertRaises(OSError):
                self.session.apply(candidate)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(backup_path.read_bytes(), backup)

    def test_secure_close_always_wipes_when_save_and_recovery_fail(self):
        self.session.entries.append(v.new_entry(title='pending'))
        self.session.dirty = True
        with patch.object(v, '_atomic_write', side_effect=OSError('simulated full disk')):
            notice = self.session.secure_close()
        self.assertIsNotNone(notice)
        self.assertFalse(any(self.session.key))
        self.assertIsNone(self.session.lock)
        with self.assertRaises(v.VaultError):
            self.session.snapshot()

    def test_stale_recovery_never_replaces_newer_vault(self):
        self.session.save_pending_recovery()
        candidate = self.session.snapshot()
        candidate['entries'].append(v.new_entry(title='newer'))
        self.session.apply(candidate)
        with self.assertRaises(v.VaultChangedError):
            self.session.apply_pending_recovery()
        self.assertEqual(self.session.entries[0]['title'], 'newer')

    def test_close_waits_for_rotation_and_wipes_new_key(self):
        entered, proceed, closed = threading.Event(), threading.Event(), threading.Event()
        failures = []
        original = v.change_master_password
        def delayed(*args, **kwargs):
            entered.set()
            if not proceed.wait(10):
                raise TimeoutError('review synchronization timeout')
            return original(*args, **kwargs)
        def rotate():
            try:
                self.session.rotate_master_password('rotated synthetic passphrase')
            except Exception as error:
                failures.append(error)
        def close():
            self.session.secure_close()
            closed.set()
        with patch.object(v, 'change_master_password', side_effect=delayed):
            writer = threading.Thread(target=rotate)
            writer.start()
            self.assertTrue(entered.wait(5))
            closer = threading.Thread(target=close)
            closer.start()
            self.assertFalse(closed.wait(0.1))
            with self.assertRaises(v.VaultBusyError):
                v.VaultSession.open(self.path, PASSWORD)
            proceed.set()
            writer.join(10)
            closer.join(10)
        self.assertFalse(failures)
        self.assertTrue(closed.is_set())
        self.assertFalse(any(self.session.key))
        self.assertIsNone(self.session.lock)
        _, key, _ = v.unlock(self.path, 'rotated synthetic passphrase')
        v.wipe_key(key)


if __name__ == '__main__':
    unittest.main(verbosity=2)
