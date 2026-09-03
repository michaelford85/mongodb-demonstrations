#!/usr/bin/env python3
"""Print Product Catalog Studio demo readiness, including index build state.

    python3 scripts/status.py

Use this to confirm both search indexes are READY before demoing the search
workspace, and to see every demo-readiness check at once.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.readiness import run_all  # noqa: E402


def main() -> None:
    print("Product Catalog Studio demo readiness\n")
    all_ok = True
    for row in run_all():
        flag = "✓" if row["ok"] else "✗"
        print(f"  {flag} {row['name']:<34} {row['detail']}")
        if not row["ok"]:
            all_ok = False
            if row["fix"]:
                print(f"      → {row['fix']}")
    print()
    if all_ok:
        print("All checks passed. Run: streamlit run app.py")
    else:
        print("Some checks need attention (see → hints above).")


if __name__ == "__main__":
    main()
