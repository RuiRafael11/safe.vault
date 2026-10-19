from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import string
import tempfile
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

APP_NAME = "Cofre Local"
FORMAT_NAME = "cofre-local"
FORMAT_VERSION = 1
AAD = b"cofre-local:v1"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**17, 8, 1
SALT_BYTES, NONCE_BYTES, KEY_BYTES = 16, 12, 32
MAX_MASTER_PASSWORD_BYTES = 1024
MAX_VAULT_BYTES = 100 * 1024 * 1024


class VaultError(Exception):
    """Erro base do cofre."""


class InvalidMasterPassword(VaultError):
    """A palavra-passe mestra está errada ou o ficheiro foi alterado."""


class InvalidVaultFile(VaultError):
    """O ficheiro não tem um formato de cofre válido."""


class VaultBusyError(VaultError):
    """O cofre já está aberto por outra instância."""


class VaultChangedError(VaultError):
    """O ficheiro foi alterado enquanto este cofre estava aberto."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: Any) -> bytes:
    if not isinstance(value, str):
        raise InvalidVaultFile("O ficheiro contém dados inválidos.")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise InvalidVaultFile("O ficheiro contém dados inválidos.") from exc


def derive_key(master_password: str, salt: bytes, *, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    if not isinstance(master_password, str):
        raise ValueError("A palavra-passe mestra não é válida.")
    password_bytes = master_password.encode("utf-8")
    if not password_bytes:
        raise ValueError("A palavra-passe mestra não pode estar vazia.")
    if len(password_bytes) > MAX_MASTER_PASSWORD_BYTES:
        raise ValueError("A palavra-passe mestra é demasiado comprida.")
    return hashlib.scrypt(password_bytes, salt=salt, n=n, r=r, p=p, maxmem=256 * 1024 * 1024, dklen=KEY_BYTES)


def empty_vault() -> dict[str, Any]:
    now = utc_now()
    return {"vault_id": str(uuid.uuid4()), "created_at": now, "updated_at": now, "entries": []}


def new_entry(*, title: str, username: str = "", password: str = "", url: str = "", category: str = "Outros", notes: str = "", favorite: bool = False) -> dict[str, Any]:
    now = utc_now()
    return {"id": str(uuid.uuid4()), "title": title.strip(), "username": username, "password": password, "url": url.strip(), "category": category.strip() or "Outros", "notes": notes, "favorite": bool(favorite), "created_at": now, "updated_at": now}


def encrypt_payload(payload: dict[str, Any], key: bytes, salt: bytes) -> dict[str, Any]:
    nonce = secrets.token_bytes(NONCE_BYTES)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, AAD)
    return {"format": FORMAT_NAME, "version": FORMAT_VERSION, "kdf": {"name": "scrypt", "salt": _b64encode(salt), "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "dklen": KEY_BYTES}, "cipher": {"name": "AES-256-GCM", "nonce": _b64encode(nonce)}, "ciphertext": _b64encode(ciphertext)}


def _validate_envelope(envelope: Any) -> tuple[bytes, bytes, dict[str, int]]:
    try:
        if not isinstance(envelope, dict):
            raise InvalidVaultFile("O ficheiro não contém um objeto válido.")
        if envelope.get("format") != FORMAT_NAME or envelope.get("version") != FORMAT_VERSION:
            raise InvalidVaultFile("Este formato de cofre não é suportado.")
        kdf, cipher = envelope["kdf"], envelope["cipher"]
        if not isinstance(kdf, dict) or not isinstance(cipher, dict):
            raise InvalidVaultFile("O ficheiro do cofre está danificado ou incompleto.")
        if kdf.get("name") != "scrypt" or cipher.get("name") != "AES-256-GCM":
            raise InvalidVaultFile("Os algoritmos deste cofre não são suportados.")
        raw = (kdf["n"], kdf["r"], kdf["p"], kdf["dklen"])
        if any(type(value) is not int for value in raw):
            raise ValueError("non-integer parameter")
        params = {"n": int(raw[0]), "r": int(raw[1]), "p": int(raw[2])}
        if params != {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P} or int(raw[3]) != KEY_BYTES:
            raise InvalidVaultFile("Os parâmetros de segurança deste cofre não são suportados.")
        salt, nonce, ciphertext = _b64decode(kdf["salt"]), _b64decode(cipher["nonce"]), _b64decode(envelope["ciphertext"])
        if len(salt) != SALT_BYTES or len(nonce) != NONCE_BYTES or len(ciphertext) < 16:
            raise InvalidVaultFile("O ficheiro do cofre está incompleto.")
        return salt, nonce, params
    except InvalidVaultFile:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise InvalidVaultFile("O ficheiro do cofre está danificado ou incompleto.") from exc


def read_envelope(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_VAULT_BYTES:
            raise InvalidVaultFile("O ficheiro é demasiado grande para ser um cofre válido.")
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except InvalidVaultFile:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidVaultFile("Não foi possível ler o ficheiro do cofre.") from exc
    _validate_envelope(data)
    return data


def unlock(path: Path, master_password: str) -> tuple[dict[str, Any], bytearray, bytes]:
    envelope = read_envelope(path)
    salt, nonce, params = _validate_envelope(envelope)
    key = derive_key(master_password, salt, **params)
    try:
        plaintext = AESGCM(key).decrypt(nonce, _b64decode(envelope["ciphertext"]), AAD)
        payload = json.loads(plaintext.decode("utf-8"))
        _validate_payload(payload)
    except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError, InvalidVaultFile) as exc:
        raise InvalidMasterPassword("A palavra-passe mestra está errada ou o ficheiro foi alterado.") from exc
    return payload, bytearray(key), salt


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise InvalidVaultFile("O conteúdo desencriptado não é válido.")
    if not isinstance(payload.get("vault_id"), str) or not payload["vault_id"]:
        raise InvalidVaultFile("O cofre não tem identificador.")
    required = {"id", "title", "username", "password", "url", "category", "notes", "favorite", "created_at", "updated_at"}
    ids: set[str] = set()
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise InvalidVaultFile("O cofre contém uma entrada inválida.")
        if not all(isinstance(entry[field], str) for field in required - {"favorite"}) or not isinstance(entry["favorite"], bool):
            raise InvalidVaultFile("O cofre contém uma entrada inválida.")
        if not entry["id"] or entry["id"] in ids:
            raise InvalidVaultFile("O cofre contém identificadores inválidos.")
        ids.add(entry["id"])


def fingerprint(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except FileNotFoundError:
        return None


class VaultFileLock:
    """Advisory OS lock held for the entire unlocked session."""
    def __init__(self, vault_path: Path) -> None:
        self.path = vault_path.with_suffix(vault_path.suffix + ".lock")
        self._handle: Any | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            raise VaultError("O bloqueio do cofre já está ativo.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if self.path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise VaultBusyError("Este cofre já está aberto noutra instância.") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise VaultBusyError("Este cofre já está aberto noutra instância.") from exc
            self._handle = handle
        except Exception:
            handle.close()
            raise

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "VaultFileLock":
        self.acquire()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.release()


def _atomic_write(path: Path, encoded: bytes) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as handle:
            temp_name = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def save(path: Path, payload: dict[str, Any], key: bytearray | bytes, salt: bytes, *, make_backup: bool = True, expected_fingerprint: str | None | object = ..., lock_held: bool = False) -> str:
    """Atomically write an encrypted payload, checking its predecessor under the OS lock."""
    path = path.resolve()
    if len(key) != KEY_BYTES or len(salt) != SALT_BYTES:
        raise VaultError("O material de cifragem da sessão não é válido.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not lock_held:
        with VaultFileLock(path):
            return save(path, payload, key, salt, make_backup=make_backup, expected_fingerprint=expected_fingerprint, lock_held=True)
    actual = fingerprint(path)
    if expected_fingerprint is not ... and actual != expected_fingerprint:
        raise VaultChangedError("O ficheiro do cofre foi alterado por outro programa; nada foi substituído.")
    candidate = deepcopy(payload)
    candidate["updated_at"] = utc_now()
    _validate_payload(candidate)
    encoded = (json.dumps(encrypt_payload(candidate, bytes(key), salt), ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    if len(encoded) > MAX_VAULT_BYTES:
        raise VaultError("O cofre excede o tamanho máximo suportado.")
    if make_backup and path.exists():
        # Never expose a partially copied backup: a failed backup leaves the
        # previous .backup untouched and aborts before replacing the vault.
        _atomic_write(path.with_suffix(path.suffix + ".backup"), path.read_bytes())
    _atomic_write(path, encoded)
    payload["updated_at"] = candidate["updated_at"]
    return hashlib.sha256(encoded).hexdigest()


def create(path: Path, master_password: str) -> tuple[dict[str, Any], bytearray, bytes]:
    path = path.resolve()
    with VaultFileLock(path):
        if path.exists():
            raise FileExistsError(path)
        salt = secrets.token_bytes(SALT_BYTES)
        key = bytearray(derive_key(master_password, salt))
        payload = empty_vault()
        try:
            save(path, payload, key, salt, make_backup=False, expected_fingerprint=None, lock_held=True)
        except Exception:
            wipe_key(key)
            raise
        return payload, key, salt


def change_master_password(path: Path, payload: dict[str, Any], current_key: bytearray, new_master_password: str, *, expected_fingerprint: str | None | object = ..., lock_held: bool = False) -> tuple[bytearray, bytes, str]:
    new_salt = secrets.token_bytes(SALT_BYTES)
    new_key = bytearray(derive_key(new_master_password, new_salt))
    try:
        new_fingerprint = save(path, payload, new_key, new_salt, make_backup=True, expected_fingerprint=expected_fingerprint, lock_held=lock_held)
    except Exception:
        wipe_key(new_key)
        raise
    wipe_key(current_key)
    return new_key, new_salt, new_fingerprint


def wipe_key(key: bytearray | None) -> None:
    if key is not None:
        for index in range(len(key)):
            key[index] = 0


def export_encrypted_copy(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        raise ValueError("Escolha um destino diferente do ficheiro aberto.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with VaultFileLock(destination.resolve()):
        _atomic_write(destination, source.read_bytes())


def generate_password(length: int = 24, *, uppercase: bool = True, lowercase: bool = True, digits: bool = True, symbols: bool = True) -> str:
    if length < 8 or length > 128:
        raise ValueError("O comprimento deve estar entre 8 e 128.")
    groups = ([string.ascii_lowercase] if lowercase else []) + ([string.ascii_uppercase] if uppercase else []) + ([string.digits] if digits else []) + (["!@#$%&*+-=?_"] if symbols else [])
    if not groups:
        raise ValueError("Selecione pelo menos um grupo de caracteres.")
    if length < len(groups):
        raise ValueError("O comprimento é insuficiente para os grupos escolhidos.")
    chars = [secrets.choice(group) for group in groups]
    alphabet = "".join(groups)
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


class VaultSnapshot(dict):
    """Detached draft with its predecessor, never serialized as vault metadata."""

    def __init__(self, payload: dict[str, Any], base_fingerprint: str | None) -> None:
        super().__init__(deepcopy(payload))
        self.base_fingerprint = base_fingerprint


@dataclass
class VaultSession:
    path: Path
    payload: dict[str, Any]
    key: bytearray
    salt: bytes
    dirty: bool = False
    expected_fingerprint: str | None = None
    lock: VaultFileLock | None = field(default=None, repr=False)
    state_lock: Any = field(default_factory=threading.RLock, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.expected_fingerprint is None:
            self.expected_fingerprint = fingerprint(self.path)

    def _ensure_open(self) -> None:
        if self._closed:
            raise VaultError("Esta sessão já foi bloqueada ou fechada.")

    @property
    def entries(self) -> list[dict[str, Any]]:
        self._ensure_open()
        return self.payload["entries"]

    def snapshot(self) -> dict[str, Any]:
        with self.state_lock:
            self._ensure_open()
            return VaultSnapshot(self.payload, self.expected_fingerprint)

    @classmethod
    def open(cls, path: Path, master_password: str) -> "VaultSession":
        path = path.resolve()
        file_lock = VaultFileLock(path)
        file_lock.acquire()
        try:
            before = fingerprint(path)
            payload, key, salt = unlock(path, master_password)
            after = fingerprint(path)
            if before != after:
                wipe_key(key)
                raise VaultChangedError("O cofre mudou durante a abertura. Volte a abri-lo.")
            return cls(path, payload, key, salt, expected_fingerprint=after, lock=file_lock)
        except Exception:
            file_lock.release()
            raise

    def persist(self) -> None:
        with self.state_lock:
            self._ensure_open()
            temporary_lock = False
            if self.lock is None:
                acquired = VaultFileLock(self.path)
                acquired.acquire()
                self.lock = acquired
                temporary_lock = True
                if self.expected_fingerprint is None:
                    self.expected_fingerprint = fingerprint(self.path)
            try:
                self.expected_fingerprint = save(self.path, self.payload, self.key, self.salt, expected_fingerprint=self.expected_fingerprint, lock_held=True)
                self.dirty = False
            finally:
                if temporary_lock and self.lock is not None:
                    self.lock.release()
                    self.lock = None

    def apply(self, candidate: dict[str, Any]) -> None:
        """Persist a detached candidate before making it the in-memory state."""
        with self.state_lock:
            self._ensure_open()
            if isinstance(candidate, VaultSnapshot) and candidate.base_fingerprint != self.expected_fingerprint:
                raise VaultChangedError("O cofre mudou desde que começou esta edição. Volte a abrir a credencial.")
            original = self.payload
            original_dirty = self.dirty
            self.payload = deepcopy(dict(candidate))
            self.dirty = True
            try:
                self.persist()
            except Exception:
                self.payload = original
                self.dirty = original_dirty
                raise

    def save_pending_recovery(self) -> Path:
        """Store an encrypted snapshot when a normal save failed, then allow locking."""
        self._ensure_open()
        pending = self.path.with_suffix(self.path.suffix + ".pending")
        candidate = deepcopy(self.payload)
        candidate["updated_at"] = utc_now()
        candidate["_cofre_recovery"] = {
            "vault_id": candidate.get("vault_id"),
            "base_fingerprint": self.expected_fingerprint,
        }
        _validate_payload(candidate)
        encoded = (json.dumps(encrypt_payload(candidate, bytes(self.key), self.salt), ensure_ascii=True, indent=2) + "\n").encode("utf-8")
        _atomic_write(pending, encoded)
        return pending

    def read_pending_recovery(self) -> dict[str, Any] | None:
        """Return a compatible encrypted recovery draft without changing the vault."""
        self._ensure_open()
        pending = self.path.with_suffix(self.path.suffix + ".pending")
        if not pending.exists():
            return None
        envelope = read_envelope(pending)
        _, nonce, _ = _validate_envelope(envelope)
        try:
            recovered = json.loads(AESGCM(bytes(self.key)).decrypt(nonce, _b64decode(envelope["ciphertext"]), AAD).decode("utf-8"))
            _validate_payload(recovered)
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError, InvalidVaultFile) as exc:
            raise InvalidVaultFile("O rascunho de recuperação está danificado.") from exc
        metadata = recovered.pop("_cofre_recovery", None)
        if not isinstance(metadata, dict) or metadata.get("vault_id") != self.payload.get("vault_id"):
            raise InvalidVaultFile("O rascunho de recuperação não pertence a este cofre.")
        if metadata.get("base_fingerprint") != self.expected_fingerprint:
            raise VaultChangedError("O cofre mudou desde o rascunho de recuperação; o rascunho não foi aplicado.")
        return recovered

    def apply_pending_recovery(self) -> bool:
        with self.state_lock:
            self._ensure_open()
            recovered = self.read_pending_recovery()
            if recovered is None:
                return False
            self.apply(recovered)
            # The commit has succeeded. A cleanup failure must not be reported
            # as a failed save; the predecessor check prevents replay next time.
            try:
                self.path.with_suffix(self.path.suffix + ".pending").unlink()
            except OSError:
                pass
            return True

    def rotate_master_password(self, new_master_password: str) -> None:
        with self.state_lock:
            self._ensure_open()
            if self.lock is None:
                raise VaultError("A sessão não tem bloqueio de ficheiro.")
            key, salt, new_fingerprint = change_master_password(self.path, self.payload, self.key, new_master_password, expected_fingerprint=self.expected_fingerprint, lock_held=True)
            self.key, self.salt, self.expected_fingerprint = key, salt, new_fingerprint
            self.dirty = False

    def secure_close(self) -> str | None:
        """Finish any writer, persist or encrypt recovery, then wipe and unlock."""
        with self.state_lock:
            recovery_error: str | None = None
            if self.dirty:
                try:
                    self.persist()
                except (VaultError, OSError) as exc:
                    try:
                        self.save_pending_recovery()
                        recovery_error = "Alterações guardadas num rascunho cifrado para recuperação"
                    except (VaultError, OSError) as recovery_exc:
                        recovery_error = f"Não foi possível guardar o rascunho antes de bloquear: {recovery_exc}"
            self.close()
            return recovery_error

    def close(self) -> None:
        with self.state_lock:
            if self._closed:
                return
            wipe_key(self.key)
            self.payload = {}
            self.salt = b""
            self.dirty = False
            if self.lock is not None:
                self.lock.release()
                self.lock = None
            self._closed = True
