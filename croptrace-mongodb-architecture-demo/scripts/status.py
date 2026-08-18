#!/usr/bin/env python3
"""Print the build status of the CropTrace Vector Search index + readiness.

    python3 scripts/status.py

Use this to confirm the vector index is READY before demoing the Knowledge
Assistant, and to see all demo-readiness checks at once.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.readiness import run_all  # noqa: E402


def main() -> None:
    print("CropTrace demo readiness\n")
    all_ok = True
    for row in run_all():
        flag = "✓" if row["ok"] else "✗"
        print(f"  {flag} {row['name']:<24} {row['detail']}")
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
