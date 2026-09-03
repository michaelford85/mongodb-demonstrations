"""Shared connection and output helpers for the pre-flight scripts.

Read-only by design: nothing here writes, drops, or reconfigures anything.
The cluster is assumed to exist already (see ../../atlas-cluster-provisioning).
"""
import os
import sys
from pathlib import Path

from pymongo import MongoClient

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:  # dotenv is optional; plain env vars work fine
    pass

SYSTEM_DATABASES = {"admin", "local", "config"}

_client = None


def get_client() -> MongoClient:
    """Return a MongoClient built from MONGODB_URI, with optional X.509 cert."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            sys.exit(
                "MONGODB_URI is not set. Export it, or copy .env.example to "
                ".env and fill it in."
            )
        cert = os.getenv("MONGODB_CERT")
        kwargs = {"serverSelectionTimeoutMS": 10000}
        if cert:
            kwargs.update(tls=True, tlsCertificateKeyFile=cert)
        _client = MongoClient(uri, **kwargs)
    return _client


def version_tuple(raw: str) -> tuple:
    """Parse '8.0.4' or '8.0.4-rc1' into (8, 0, 4)."""
    parts = []
    for piece in raw.split("-")[0].split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def target_databases(requested: list = None) -> list:
    """Databases to inspect: --db args, else DB_NAMES, else all non-system."""
    if requested:
        return requested
    from_env = os.getenv("DB_NAMES", "").strip()
    if from_env:
        return [name.strip() for name in from_env.split(",") if name.strip()]
    return [
        name
        for name in get_client().list_database_names()
        if name not in SYSTEM_DATABASES
    ]


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def section(title: str) -> None:
    print()
    print(f"-- {title} " + "-" * max(0, 74 - len(title)))


def kv(label: str, value, width: int = 28) -> None:
    dots = "." * max(1, width - len(label))
    print(f"  {label} {dots} {value}")


def ok(message: str) -> None:
    print(f"  [ ok ]   {message}")


def warn(message: str) -> None:
    print(f"  [ warn ] {message}")


def note(message: str) -> None:
    print(f"  [ note ] {message}")


def table(rows: list, columns: list) -> None:
    if not rows:
        print("  (nothing to report)")
        return
    widths = [
        max(len(col), *(len(str(r.get(col, ""))) for r in rows)) for col in columns
    ]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*columns))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*(str(row.get(col, "")) for col in columns)))


def footer(findings: list) -> None:
    """Close every report the same way so notes stay comparable across runs."""
    section("Summary")
    if not findings:
        ok("no follow-up items detected by this check")
        return
    for finding in findings:
        warn(finding)
    print()
    note(f"{len(findings)} item(s) to review before upgrading")
