"""One-off local helper: build atlas-iceberg-demo/.env from the sibling
atlas-cluster-provisioning project.

Combines the Terraform ``standard_srv`` output with DB_ADMIN_USER /
DB_ADMIN_PASSWORD from that project's .env to form MONGODB_URI. Secrets are
never printed. Intended for local demo runs only; not part of the demo flow.
"""

import json
import pathlib
import subprocess
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PROV = ROOT / "atlas-cluster-provisioning"
DEMO = ROOT / "atlas-iceberg-demo"


def load_env(path: pathlib.Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> None:
    prov_env = load_env(PROV / ".env")
    user = prov_env["DB_ADMIN_USER"]
    pw = prov_env["DB_ADMIN_PASSWORD"]

    srv = json.loads(subprocess.check_output(
        ["terraform", "output", "-json", "connection_strings"], cwd=PROV
    ))["standard_srv"]

    host = srv.split("://", 1)[1]
    uri = f"mongodb+srv://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(pw)}@{host}"
    uri += ("&" if "?" in uri else "/?") + "retryWrites=true&w=majority"

    lines = []
    for line in (DEMO / ".env.example").read_text().splitlines():
        lines.append(f"MONGODB_URI={uri}" if line.startswith("MONGODB_URI=") else line)
    (DEMO / ".env").write_text("\n".join(lines) + "\n")

    print("Wrote atlas-iceberg-demo/.env")
    print("MONGODB_URI configured (value redacted):", uri.startswith("mongodb+srv://"))


if __name__ == "__main__":
    main()
