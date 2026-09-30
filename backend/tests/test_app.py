import httpx
import pytest
from fastapi import FastAPI

from app.config import BACKEND_DIR, Settings
from app.main import SPAStaticFiles


@pytest.fixture
async def spa_client(tmp_path):
    (tmp_path / "index.html").write_text("<html>app</html>")
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=tmp_path, html=True))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_frontend_routes_fall_back_to_index_html(spa_client):
    response = await spa_client.get("/watches/12")

    assert response.status_code == 200
    assert "app" in response.text


async def test_unknown_api_path_is_a_404_not_html(spa_client):
    response = await spa_client.get("/api/watchs")

    assert response.status_code == 404


def test_default_db_is_in_backend_folder(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(_env_file=None, session_secret="x")

    assert settings.database_url == (
        f"sqlite+aiosqlite:///{(BACKEND_DIR / 'sitemonitor.db').as_posix()}"
    )
