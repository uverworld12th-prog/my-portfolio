import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture
def cfg():
    from lib.config import load_config
    return load_config()


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("DRAFTS_DB_PATH", str(p))
    return p
