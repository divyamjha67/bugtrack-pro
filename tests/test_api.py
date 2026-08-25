from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


TEST_DB = Path(__file__).parent / "test_bugtrack.db"
test_engine = create_engine(f"sqlite:///{TEST_DB}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def setup_module():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def teardown_module():
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


def test_health():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_issue_lifecycle():
    client = TestClient(app)
    registration = client.post("/api/auth/register", json={"name":"Asha Developer", "email":"asha@example.com", "password":"password123"})
    assert registration.status_code == 201
    token = registration.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/issues", headers=auth, json={"title":"Login button is unresponsive", "description":"Clicking login does not submit the form.", "priority":"high"})
    assert created.status_code == 201
    issue_id = created.json()["id"]
    assert created.json()["status"] == "open"

    updated = client.patch(f"/api/issues/{issue_id}", headers=auth, json={"status":"in_progress"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"

    comment = client.post(f"/api/issues/{issue_id}/comments", headers=auth, json={"body":"I can reproduce this on Chrome."})
    assert comment.status_code == 201
    assert comment.json()["body"] == "I can reproduce this on Chrome."

    listed = client.get("/api/issues?status=in_progress", headers=auth)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == issue_id


def test_invalid_credentials_are_rejected():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"email":"asha@example.com", "password":"wrong-password"})
    assert response.status_code == 401
