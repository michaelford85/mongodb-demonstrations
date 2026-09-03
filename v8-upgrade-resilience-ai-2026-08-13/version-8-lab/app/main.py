"""Version 8 feature sampler — CLI entry point.

    python app/main.py seed [--drop]   load the synthetic data and the index
    python app/main.py uuid            $toUUID: 7.x pattern vs 8.x pattern
    python app/main.py settings        query settings: block or pin a shape
    python app/main.py all [--drop]    seed, then run both demos
    python app/main.py clean           remove query settings and lab data
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import demo_settings  # noqa: E402
import demo_uuid  # noqa: E402
from config import DB_NAME, get_client, require_v8  # noqa: E402
from seed import seed  # noqa: E402


def _clean() -> None:
    demo_settings._remove_settings()
    get_client().drop_database(DB_NAME)
    print(f"Removed query settings and dropped database {DB_NAME}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MongoDB 8 feature sampler: 7.x patterns vs 8.x patterns."
    )
    parser.add_argument("command",
                        choices=["seed", "uuid", "settings", "all", "clean"])
    parser.add_argument("--drop", action="store_true",
                        help="drop and reload the seed data")
    parser.add_argument("--keep-settings", action="store_true",
                        help="leave the query settings in place after the "
                             "settings demo so you can inspect them")
    args = parser.parse_args()

    if args.command == "clean":
        _clean()
        return

    version = require_v8()
    print(f"Connected to MongoDB {'.'.join(str(p) for p in version)}, "
          f"database {DB_NAME}")

    if args.command in ("seed", "all"):
        seed(drop=args.drop)
    if args.command in ("uuid", "all"):
        demo_uuid.run()
    if args.command in ("settings", "all"):
        demo_settings.run(keep=args.keep_settings)


if __name__ == "__main__":
    main()
