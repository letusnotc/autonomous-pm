"""
Test setup: a throwaway SQLite database, recreated for every test, and an
HTTP client that talks to the FastAPI app in-process.
"""
import os
import tempfile
from pathlib import Path

# Must be set before the app (and its database engine) is imported.
_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_BACKEND"] = "sql"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB.as_posix()}"

import httpx  # noqa: E402
import pytest  # noqa: E402

from src import database, models  # noqa: E402,F401
from src.main import app  # noqa: E402


@pytest.fixture
async def client():
    async with database.engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.drop_all)
    await database.init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await database.engine.dispose()   # connections are bound to this test's event loop


@pytest.fixture
def create(client):
    async def _create(title, **fields):
        resp = await client.post("/tickets", json={"title": title, **fields})
        assert resp.status_code == 201, resp.text
        return resp.json()
    return _create


@pytest.fixture
def events(client):
    async def _events(ticket_id):
        resp = await client.get(f"/tickets/{ticket_id}/events")
        assert resp.status_code == 200, resp.text
        return resp.json()
    return _events
