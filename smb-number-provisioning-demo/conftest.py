"""Pytest bootstrap: put the demo root on sys.path so `import lib...` works,
and provide the shared in-memory `db` fixture (mongomock, offline)."""

import sys
from pathlib import Path

import mongomock
import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture()
def db():
    from lib.sample_data import account_docs
    client = mongomock.MongoClient()
    database = client["smb_number_demo"]
    database["numberAssets"].create_index(
        [("accountId", 1), ("tn.orig.startTn", 1), ("type", 1)],
        unique=True)
    database["provisioningCounters"].create_index(
        [("accountId", 1), ("capType", 1)], unique=True)
    for doc in account_docs():
        database["accounts"].insert_one(dict(doc))
    return database
