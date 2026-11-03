"""Pytest bootstrap: put the demo root on sys.path so `import lib...` works."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
