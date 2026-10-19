from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cofre_local.ui_flet.motion import MotionSystem, system_animations_enabled
from cofre_local.ui_flet.preferences import load_preferences, save_preferences
from cofre_local.ui_flet.theme import DEFAULT_THEME, PALETTES, get_palette


class ThemeTests(unittest.TestCase):
    def test_all_approved_themes_exist(self) -> None:
        self.assertEqual(set(PALETTES), {"pearl", "midnight", "aurora", "graphite"})
        for key, palette in PALETTES.items():
            self.assertEqual(palette.key, key)
            self.assertTrue(palette.accent.startswith("#"))
            self.assertTrue(palette.text.startswith("#"))

    def test_unknown_theme_falls_back_to_pearl(self) -> None:
        self.assertEqual(get_palette("not-a-theme").key, DEFAULT_THEME)


class MotionTests(unittest.TestCase):
    def test_non_windows_defaults_to_motion(self) -> None:
        with patch("cofre_local.ui_flet.motion.sys.platform", "linux"):
            self.assertTrue(system_animations_enabled())

    def test_disabled_motion_uses_zero_durations(self) -> None:
        with patch("cofre_local.ui_flet.motion.system_animations_enabled", return_value=False):
            motion = MotionSystem.from_system()
        self.assertFalse(motion.enabled)
        self.assertEqual((motion.quick_ms, motion.standard_ms, motion.deliberate_ms), (0, 0, 0))


class PreferencesTests(unittest.TestCase):
    def test_preferences_round_trip_and_clamp(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            save_preferences(
                {"theme": "midnight", "recent_vault": "C:/x.vault", "auto_lock_minutes": 99}, path
            )
            restored = load_preferences(path)
            self.assertEqual(restored["theme"], "midnight")
            self.assertEqual(restored["recent_vault"], "C:/x.vault")
            self.assertEqual(restored["auto_lock_minutes"], 60)

    def test_corrupt_preferences_use_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_preferences(path)["theme"], DEFAULT_THEME)

    def test_invalid_theme_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            path.write_text(json.dumps({"theme": "unknown"}), encoding="utf-8")
            self.assertEqual(load_preferences(path)["theme"], DEFAULT_THEME)


if __name__ == "__main__":
    unittest.main()
