import os

# Configure before importing the app: settings and the engine read env at import time.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://zela:zela@localhost:5433/zela_test"
)
os.environ.update(
    ENV="test",
    AUTH_MODE="dev",
    DATABASE_URL=TEST_DATABASE_URL,
    WHATSAPP_APP_SECRET="test-app-secret",
    WHATSAPP_VERIFY_TOKEN="test-verify-token",
)

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from tests.factories import World, build_world  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    # Running the real migrations doubles as a test that they apply cleanly.
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    def _get_db() -> Iterator[Session]:
        try:
            yield db
        finally:
            # Like a closed request session in production: drop anything uncommitted.
            db.rollback()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def world(db: Session) -> World:
    return build_world(db)
