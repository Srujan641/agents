import pytest
from meeting_agent.storage import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "nested" / "test.db")
