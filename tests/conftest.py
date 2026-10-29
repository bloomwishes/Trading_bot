"""
AutoTrader Pro - Pytest Configuration & Global Fixtures
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_DB_FILE = PROJECT_ROOT / "test_autotrader.db"
if TEST_DB_FILE.exists():
    try:
        TEST_DB_FILE.unlink()
    except Exception:
        pass

# Enforce test environment variables
os.environ["DB_PATH"] = str(TEST_DB_FILE)
os.environ["API_KEY"] = "test-secret-key"
os.environ["PAPER_MODE"] = "true"
os.environ["BACKEND_HOST"] = "127.0.0.1"

from backend.config import settings
settings.DB_PATH = str(TEST_DB_FILE)
settings.API_KEY = "test-secret-key"

import backend.database as db_mod
test_engine = create_engine(
    f"sqlite:///{TEST_DB_FILE}",
    connect_args={"check_same_thread": False},
    echo=False,
    pool_pre_ping=True,
)
db_mod.engine = test_engine
db_mod.SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)

from backend.database import init_db, SessionLocal, get_db
from backend.main import app

# Ensure FastAPI uses the isolated test DB session
def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Initialise isolated test database and configuration."""
    init_db()
    yield
    # Teardown
    db_mod.engine.dispose()
    if TEST_DB_FILE.exists():
        try:
            TEST_DB_FILE.unlink()
        except Exception:
            pass


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    """Database session fixture."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_headers():
    """Standard authentication headers fixture."""
    return {"X-API-Key": "test-secret-key"}
