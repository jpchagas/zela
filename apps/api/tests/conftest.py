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
    # Tests run jobs explicitly; nothing may run on background threads.
    JOBS_MODE="log",
)

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.jobs import get_job_publisher  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.integrations.google.factory import get_google  # noqa: E402
from app.integrations.google.fake import FakeGoogle  # noqa: E402
from app.integrations.storage import LocalBlobStore, get_blob_store  # noqa: E402
from app.main import app  # noqa: E402
from tests.factories import FakePublisher, World, build_world  # noqa: E402


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
def store(tmp_path):
    blob_store = LocalBlobStore(str(tmp_path / "uploads"))
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    return blob_store


@pytest.fixture
def publisher():
    """Collects published jobs; tests run them explicitly."""
    fake = FakePublisher()
    app.dependency_overrides[get_job_publisher] = lambda: fake
    return fake


@pytest.fixture
def google():
    """In-memory Google Drive; tests read and hand-edit its spreadsheets."""
    fake = FakeGoogle()
    app.dependency_overrides[get_google] = lambda: fake
    return fake


@pytest.fixture
def world(db: Session) -> World:
    return build_world(db)
