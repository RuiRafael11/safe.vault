from pathlib import Path
import sys

# Allow `python run_cofre.py` in a clean checkout without installing the
# package first. The packaged executable resolves imports normally.
SOURCE = Path(__file__).resolve().parent / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from cofre_local.app import run

if __name__ == "__main__":
    run()
