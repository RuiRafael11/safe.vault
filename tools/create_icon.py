"""Compatibility entry point for regenerating the current Windows identity."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("create_brand_icon.py")), run_name="__main__")
