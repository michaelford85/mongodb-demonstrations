#!/usr/bin/env python3
"""Print every demo-readiness check from the command line.

    python3 scripts/status.py

Run this before the session. No secret is printed — the URI check reports
presence only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.readiness import run_all  # noqa: E402


def main() -> int:
    print("MongoDB Foundations walkthrough — demo readiness\n")
    rows = run_all()
    for row in rows:
        print("  {} {:<24} {}".format("✓" if row["ok"] else "✗",
                                      row["name"], row["detail"]))
        if not row["ok"] and row["fix"]:
            print("      → {}".format(row["fix"]))
    print()
    if all(r["ok"] for r in rows):
        print("All checks passed. Run: streamlit run app.py")
        return 0
    print("Some checks need attention (see → hints above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
