from __future__ import annotations

import re
import unittest
from pathlib import Path

from cofre_local import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class VersioningTests(unittest.TestCase):
    def test_package_version_is_semantic(self) -> None:
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_build_reads_the_package_version(self) -> None:
        build_script = (PROJECT_ROOT / "tools" / "build.ps1").read_text(encoding="utf-8")

        self.assertIn("from cofre_local import __version__", build_script)
        self.assertIn("--product-version $version", build_script)
        self.assertIn("--file-version $fileVersion", build_script)
        self.assertIsNone(re.search(r"--product-version\s+\d", build_script))


if __name__ == "__main__":
    unittest.main()
