"""
AutoTrader Pro - Pytest Configuration & Global Fixtures
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enforce test environment variables
os.environ["API_KEY"] = "test-secret-key"
os.environ["PAPER_MODE"] = "true"
os.environ["BACKEND_HOST"] = "127.0.0.1"

from backend.config import settings
settings.API_KEY = "test-secret-key"

from backend.database import init_db, SessionLocal
from backend.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Initialise test database and configuration."""
    init_db()


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
