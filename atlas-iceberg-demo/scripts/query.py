"""Run the demo SQL against the Iceberg table via Trino.

Executes each statement in sql/queries.sql (separated by lines of "-- @@")
and prints a compact result table — the live order plus analytical
aggregations (volume and notional value by symbol).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import iceberg_io

log = common.get_logger("query")

QUERIES_FILE = common.DEMO_DIR / "sql" / "queries.sql"


def load_statements() -> list[str]:
    raw = QUERIES_FILE.read_text()
    blocks, current = [], []
    for line in raw.splitlines():
        if line.strip() == "-- @@":
            blocks.append(current)
            current = []
        else:
            current.append(line)
    blocks.append(current)

    statements = []
    for block in blocks:
        lines = [ln for ln in block if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip().rstrip(";").strip()
        if stmt:
            statements.append(stmt)
    return statements


def print_table(cols: list[str], rows: list) -> None:
    if not cols:
        print("(no result set)")
        return
    widths = [len(c) for c in cols]
    str_rows = [[("" if v is None else str(v)) for v in row] for row in rows]
    for r in str_rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*cols))
    print("  ".join("-" * w for w in widths))
    for r in str_rows:
        print(fmt.format(*r))
    print(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")


def main() -> None:
    common.banner("QUERY · Iceberg via Trino SQL")
    conn = iceberg_io.trino_connection()
    for i, stmt in enumerate(load_statements(), 1):
        print(f"\n--- Query {i} " + "-" * 54)
        print(stmt)
        print()
        cols, rows = iceberg_io.run_query(conn, stmt)
        print_table(cols, rows)


if __name__ == "__main__":
    main()
