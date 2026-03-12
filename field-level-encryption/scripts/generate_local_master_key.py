from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from common import ensure_local_master_key


def main() -> None:
    load_dotenv()
    path = Path(os.environ.get("LOCAL_MASTER_KEY_PATH", ".keys/local-master-key.bin"))
    ensure_local_master_key(path)
    print(f"Local master key is ready at {path}.")


if __name__ == "__main__":
    main()
