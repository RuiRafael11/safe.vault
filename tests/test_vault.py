from __future__ import annotations

import json
import string
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cofre_local.vault import (
    InvalidMasterPassword,
    InvalidVaultFile,
    VaultSession,
    change_master_password,
    create,
    generate_password,
    new_entry,
    read_envelope,
    unlock,
)


class VaultTests(unittest.TestCase):
    def test_create_save_and_unlock_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.vault"
            payload, key, salt = create(path, "frase mestra muito comprida 123")
            session = VaultSession(path, payload, key, salt)
            entry = new_entry(
                title="Banco",
                username="pessoa@example.com",
                password="segredo-longo",
                url="https://example.com",
                notes="nota confidencial",
                category="Finanças",
                favorite=True,
            )
            session.entries.append(entry)
            session.persist()
            session.close()

            restored, restored_key, restored_salt = unlock(path, "frase mestra muito comprida 123")
            self.assertEqual(restored["entries"][0]["password"], "segredo-longo")
            self.assertEqual(restored["entries"][0]["notes"], "nota confidencial")
            self.assertTrue(restored["entries"][0]["favorite"])
            self.assertEqual(len(restored_key), 32)
            self.assertEqual(len(restored_salt), 16)

    def test_wrong_password_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.vault"
            create(path, "frase mestra correta e longa")
            with self.assertRaises(InvalidMasterPassword):
                unlock(path, "frase mestra errada e longa")

    def test_ciphertext_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.vault"
            create(path, "frase mestra correta e longa")
            envelope = json.loads(path.read_text(encoding="utf-8"))
            ciphertext = envelope["ciphertext"]
            envelope["ciphertext"] = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
            path.write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaises(InvalidMasterPassword):
                unlock(path, "frase mestra correta e longa")

    def test_backup_is_previous_encrypted_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.vault"
            payload, key, salt = create(path, "frase mestra correta e longa")
            session = VaultSession(path, payload, key, salt)
            session.entries.append(new_entry(title="Primeira", password="abc"))
            session.persist()
            backup = path.with_suffix(".vault.backup")
            self.assertTrue(backup.exists())
            old, old_key, _ = unlock(backup, "frase mestra correta e longa")
            self.assertEqual(old["entries"], [])
            for index in range(len(old_key)):
                old_key[index] = 0

    def test_password_generator_uses_selected_groups(self) -> None:
        value = generate_password(40)
        self.assertEqual(len(value), 40)
        self.assertTrue(any(c in string.ascii_lowercase for c in value))
        self.assertTrue(any(c in string.ascii_uppercase for c in value))
        self.assertTrue(any(c in string.digits for c in value))
        self.assertTrue(any(c in "!@#$%&*+-=?_" for c in value))
        self.assertNotEqual(value, generate_password(40))

    def test_failed_transaction_does_not_duplicate_or_mutate_live_entries(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.vault"
            payload, key, salt = create(path, "frase mestra correta e longa")
            session = VaultSession(path, payload, key, salt)
            candidate = session.snapshot()
            candidate["entries"].append(new_entry(title="Não deve ficar"))
            with patch("cofre_local.vault.save", side_effect=OSError("disco cheio")):
                with self.assertRaises(OSError):
                    session.apply(candidate)
            self.assertEqual(session.entries, [])
            self.assertFalse(session.dirty)
            session.apply(candidate)
            self.assertEqual([entry["title"] for entry in session.entries], ["Não deve ficar"])
            session.close()

    def test_rotation_keeps_previous_backup_with_old_master_password(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.vault"
            payload, key, salt = create(path, "palavra-passe antiga muito longa")
            session = VaultSession(path, payload, key, salt)
            session.entries.append(new_entry(title="Banco"))
            session.persist()
            old_password = "palavra-passe antiga muito longa"
            new_password = "palavra-passe nova muito longa"
            new_key, new_salt, _ = change_master_password(path, session.payload, session.key, new_password)
            session.key, session.salt = new_key, new_salt
            restored, restored_key, _ = unlock(path, new_password)
            self.assertEqual(restored["entries"][0]["title"], "Banco")
            previous, previous_key, _ = unlock(path.with_suffix(".vault.backup"), old_password)
            self.assertEqual(previous["entries"][0]["title"], "Banco")
            for material in (restored_key, previous_key):
                for index in range(len(material)):
                    material[index] = 0
            session.close()

    def test_malformed_envelopes_are_rejected_as_invalid_vaults(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.vault"
            for value in ({"format": "cofre-local", "version": 1, "kdf": [], "cipher": None}, b"\xff\xfe"):
                if isinstance(value, bytes):
                    path.write_bytes(value)
                else:
                    path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(InvalidVaultFile):
                    read_envelope(path)

    def test_pending_recovery_is_encrypted_and_requires_explicit_apply(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.vault"
            payload, key, salt = create(path, "frase mestra correta e longa")
            session = VaultSession(path, payload, key, salt)
            session.entries.append(new_entry(title="Rascunho"))
            session.dirty = True
            pending = session.save_pending_recovery()
            self.assertNotIn(b"Rascunho", pending.read_bytes())
            self.assertEqual(unlock(path, "frase mestra correta e longa")[0]["entries"], [])
            self.assertEqual(session.read_pending_recovery()["entries"][0]["title"], "Rascunho")
            session.apply_pending_recovery()
            self.assertFalse(pending.exists())
            self.assertEqual(unlock(path, "frase mestra correta e longa")[0]["entries"][0]["title"], "Rascunho")
            session.close()


if __name__ == "__main__":
    unittest.main()
