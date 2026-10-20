import pytest

from daymark.store import Daymark


@pytest.fixture
def app(tmp_path):
    store = Daymark(tmp_path / "daymark.db")
    try:
        yield store
    finally:
        store.close()
