import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import db

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def dbfile(tmp_path):
    """One database per test, shared by every fixture that wants it.

    `client` and `conn` must point at the same file: a test that sets up through
    the connection and asserts through the API is otherwise quietly talking to
    two different databases, and passes or fails for reasons that have nothing
    to do with the code.
    """
    db.DB_PATH = str(tmp_path / "test.db")
    connection = db.connect()
    db.init_db(connection)
    connection.close()
    return db.DB_PATH


@pytest.fixture()
def client(dbfile):
    import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture()
def conn(dbfile):
    connection = db.connect()
    yield connection
    connection.close()


def add(client, title, **fields):
    """Create a task and optionally patch it in one step."""
    task = client.post("/api/tasks", json={"title": title}).json()
    if fields:
        task = client.patch(f"/api/tasks/{task['id']}", json=fields).json()
    return task
