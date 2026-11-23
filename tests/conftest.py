from pathlib import Path

import pytest

from fixforge.config import Settings
from fixforge.engine import Engine
from fixforge.fixtures import FIXTURES
from fixforge.store import Store


@pytest.fixture
def setup_engine(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    store = Store(tmp_path)
    return Engine(settings, store), store


def create_fixture(store: Store, fixture_id: str = "payment-zero") -> dict:
    fixture = FIXTURES[fixture_id]
    values = fixture.public()
    values.pop("id")
    return store.create(provider="demo", fixture_id=fixture_id, **values)
