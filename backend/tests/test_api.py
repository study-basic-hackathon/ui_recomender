import uuid

import pytest
from fastapi.testclient import TestClient

from app.di.dependencies import get_db
from app.main import app
from app.model.session import (
    Iteration,
    IterationStatus,
    Proposal,
    ProposalStatus,
    Session,
)
from app.repository.iteration_repository import IterationRepository
from app.repository.proposal_repository import ProposalRepository
from app.repository.session_repository import SessionRepository


@pytest.fixture()
def client(db):
    """Create a test client with overridden dependencies."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def sample_session(db) -> Session:
    """Create a sample session with iteration 0."""
    session_repo = SessionRepository(db)
    session = session_repo.create(
        Session(
            repo_url="https://github.com/test/repo",
            base_branch="main",
        )
    )
    iter_repo = IterationRepository(db)
    iter_repo.create(
        Iteration(
            session_id=session.id,
            iteration_index=0,
            instruction="Make the header blue",
            status=IterationStatus.PENDING,
        )
    )
    db.refresh(session)
    return session


@pytest.fixture()
def completed_session(db) -> Session:
    """Create a session with completed iteration and proposals."""
    session_repo = SessionRepository(db)
    session = session_repo.create(
        Session(
            repo_url="https://github.com/test/repo",
            base_branch="main",
        )
    )
    iter_repo = IterationRepository(db)
    iteration = iter_repo.create(
        Iteration(
            session_id=session.id,
            iteration_index=0,
            instruction="Redesign the navbar",
            status=IterationStatus.COMPLETED,
        )
    )
    prop_repo = ProposalRepository(db)
    for i in range(2):
        prop_repo.create(
            Proposal(
                iteration_id=iteration.id,
                proposal_index=i,
                title=f"Proposal {i}",
                concept=f"Concept {i}",
                plan='["step 1"]',
                files='[{"path": "src/App.tsx"}]',
                complexity="medium",
                status=ProposalStatus.COMPLETED,
            )
        )
    db.refresh(session)
    return session


class TestListSessions:
    def test_empty_list(self, client):
        response = client.get("/api/sessions/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_with_sessions(self, client, sample_session):
        response = client.get("/api/sessions/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["repo_url"] == "https://github.com/test/repo"


class TestGetSession:
    def test_get_existing(self, client, sample_session):
        response = client.get(f"/api/sessions/{sample_session.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_session.id)
        assert data["status"] == "active"
        assert len(data["iterations"]) == 1
        assert data["iterations"][0]["instruction"] == "Make the header blue"

    def test_get_nonexistent(self, client):
        response = client.get(f"/api/sessions/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_with_proposals(self, client, completed_session):
        response = client.get(f"/api/sessions/{completed_session.id}")
        assert response.status_code == 200
        data = response.json()
        iteration = data["iterations"][0]
        assert iteration["status"] == "completed"
        assert len(iteration["proposals"]) == 2
        assert iteration["proposals"][0]["title"] == "Proposal 0"
        assert iteration["proposals"][0]["plan"] == ["step 1"]


class TestCreateSession:
    def test_create_success(self, client, monkeypatch):
        import app.usecase.session_usecase as usecase_mod

        monkeypatch.setattr(usecase_mod.asyncio, "create_task", lambda coro: coro.close())
        monkeypatch.setattr("app.service.s3_service.S3Service._ensure_bucket", lambda self: None)

        response = client.post(
            "/api/sessions/",
            json={
                "repo_url": "https://github.com/new/repo",
                "branch": "develop",
                "instruction": "Add dark mode",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["repo_url"] == "https://github.com/new/repo"
        assert data["base_branch"] == "develop"
        assert data["status"] == "active"

    def test_create_missing_fields(self, client):
        response = client.post("/api/sessions/", json={})
        assert response.status_code == 422


class TestSettingsAPI:
    def test_list_settings_empty(self, client):
        response = client.get("/api/settings/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_and_list_setting(self, client):
        response = client.post("/api/settings/", json={"key": "max_proposals", "value": "5"})
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "max_proposals"
        assert data["value"] == "5"

        response = client.get("/api/settings/")
        settings = response.json()
        keys = [s["key"] for s in settings]
        assert "max_proposals" in keys

    def test_update_setting(self, client):
        client.post("/api/settings/", json={"key": "theme", "value": "dark"})
        response = client.post("/api/settings/", json={"key": "theme", "value": "light"})
        assert response.status_code == 200
        assert response.json()["value"] == "light"
