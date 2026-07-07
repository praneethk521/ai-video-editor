from __future__ import annotations

import os
from pathlib import Path

os.environ["API_TOKEN"] = "test-token"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{Path(__file__).parent / 'test.sqlite3'}"
os.environ["RENDER_QUEUE_BACKEND"] = "database"

import pytest
from fastapi.testclient import TestClient

from app.db.session import Base, engine
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}
