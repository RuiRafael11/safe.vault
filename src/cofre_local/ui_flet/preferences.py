from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .theme import DEFAULT_THEME, PALETTES


def app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    result = base / "Cofre Local"
    result.mkdir(parents=True, exist_ok=True)
    return result


def preferences_path() -> Path:
    return app_data_dir() / "preferences.json"


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    target = path or preferences_path()
    defaults: dict[str, Any] = {
        "theme": DEFAULT_THEME,
        "recent_vault": "",
        "auto_lock_minutes": 5,
    }
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    theme = str(raw.get("theme", DEFAULT_THEME)).lower()
    defaults["theme"] = theme if theme in PALETTES else DEFAULT_THEME
    defaults["recent_vault"] = str(raw.get("recent_vault", ""))
    try:
        minutes = int(raw.get("auto_lock_minutes", 5))
    except (TypeError, ValueError):
        minutes = 5
    defaults["auto_lock_minutes"] = min(60, max(1, minutes))
    return defaults


def save_preferences(values: dict[str, Any], path: Path | None = None) -> None:
    target = path or preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "theme": values.get("theme", DEFAULT_THEME),
        "recent_vault": values.get("recent_vault", ""),
        "auto_lock_minutes": values.get("auto_lock_minutes", 5),
    }
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        temp_name = None
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
