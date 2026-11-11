import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # fresh database per test, LLM always off so tests are deterministic and free
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_MODE", "off")
    from app.main import app

    with TestClient(app) as c:
        yield c


A = "atlas-marrakech"
B = "blue-coast-agadir"
