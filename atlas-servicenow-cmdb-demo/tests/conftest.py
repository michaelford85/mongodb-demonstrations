import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
sys.path.insert(0, str(DEMO))

from config import load_mapping
from mock_atlas import MockAtlasClient
from normalizer import normalize_inventory
from ire_payload import build_ire_payload


@pytest.fixture
def mapping():
    return load_mapping(DEMO / "mapping.json")


@pytest.fixture
def mock_inventory():
    return MockAtlasClient()


@pytest.fixture
def normalized(mock_inventory, mapping):
    return normalize_inventory(mock_inventory, mapping)
