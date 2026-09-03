"""Preflight checks + bounded readiness polling for the local stack.

Modes:
  (default)      full check: Python, Docker, Atlas + change-stream eligibility,
                 and that MinIO / REST catalog / Trino are reachable.
  --infra-only   skip the Atlas checks (used right after `docker compose up`).
  --wait N       poll the infra endpoints for up to N seconds instead of failing
                 immediately (health-check style, no arbitrary sleeps).
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

log = common.get_logger("preflight")


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _wait_for(desc: str, url: str, timeout: int) -> bool:
    deadline = time.time() + max(timeout, 0)
    while True:
        if _http_ok(url):
            log.info("OK   %s", desc)
            return True
        if time.time() >= deadline:
            log.error("FAIL %s (%s not reachable)", desc, url)
            return False
        time.sleep(1)


def check_python() -> bool:
    ok = sys.version_info >= (3, 12)
    (log.info if ok else log.warning)(
        "%s Python %d.%d (3.12 recommended)",
        "OK  " if ok else "WARN", sys.version_info.major, sys.version_info.minor)
    return True


def check_docker() -> bool:
    if not shutil.which("docker"):
        log.error("FAIL docker CLI not found on PATH")
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        log.info("OK   Docker daemon running")
        return True
    except Exception:
        log.error("FAIL Docker daemon not running — start Docker Desktop")
        return False


def check_atlas() -> bool:
    try:
        client = common.get_mongo_client()
        client.admin.command("ping")
        if not common.supports_change_streams(client):
            log.error("FAIL Atlas reachable but not change-stream eligible "
                      "(needs a replica set / sharded cluster)")
            client.close()
            return False
        log.info("OK   Atlas reachable and change-stream eligible")
        client.close()
        return True
    except Exception as e:
        log.error("FAIL Atlas connection: %s", type(e).__name__)
        log.error("     Check MONGODB_URI in .env and your Atlas IP Access List.")
        return False


def check_infra(timeout: int) -> bool:
    targets = [
        ("MinIO (S3)", f"{common.S3_ENDPOINT}/minio/health/live"),
        ("Iceberg REST catalog", f"{common.ICEBERG_REST_URI}/v1/config?warehouse={common.ICEBERG_WAREHOUSE}"),
        ("Trino query engine", f"http://{common.TRINO_HOST}:{common.TRINO_PORT}/v1/info"),
    ]
    return all(_wait_for(desc, url, timeout) for desc, url in targets)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight checks")
    parser.add_argument("--infra-only", action="store_true")
    parser.add_argument("--wait", type=int, default=0, help="poll infra up to N seconds")
    args = parser.parse_args()

    common.banner("PREFLIGHT · environment checks")
    results = [check_python(), check_docker()]
    if not args.infra_only:
        results.append(check_atlas())
    results.append(check_infra(args.wait))

    if all(results):
        log.info("All checks passed.")
    else:
        log.error("One or more checks failed — see messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
