import uuid

import pytest
from fastapi.testclient import TestClient

from app.di.dependencies import get_db
from app.main import app
from app.model.job import Job, JobStatus, Proposal


@pytest.fixture()
def client(db):
    """Create a test client with overridden DB dependency."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def sample_job(db) -> Job:
    """Create a sample job in the DB."""
    from app.repository.job_repository import JobRepository

    repo = JobRepository(db)
    return repo.create(
        Job(
            repo_url="https://github.com/test/repo",
            branch="main",
            instruction="Make the header blue",
        )
    )


@pytest.fixture()
def analyzed_job(db) -> Job:
    """Create a job in analyzed state with proposals."""
    from app.repository.job_repository import JobRepository
    from app.repository.proposal_repository import ProposalRepository

    job_repo = JobRepository(db)
    job = job_repo.create(
        Job(
            repo_url="https://github.com/test/repo",
            branch="main",
            instruction="Redesign the navbar",
            status=JobStatus.ANALYZED,
        )
    )

    prop_repo = ProposalRepository(db)
    for i in range(2):
        prop_repo.create(
            Proposal(
                job_id=job.id,
                proposal_index=i,
                title=f"Proposal {i}",
                concept=f"Concept {i}",
                plan='["step 1"]',
                files='[{"path": "src/App.tsx"}]',
                complexity="medium",
            )
        )

    db.refresh(job)
    return job


class TestListJobs:
    def test_empty_list(self, client):
        response = client.get("/api/jobs/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_with_jobs(self, client, sample_job):
        response = client.get("/api/jobs/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["repo_url"] == "https://github.com/test/repo"


class TestGetJob:
    def test_get_existing(self, client, sample_job):
        response = client.get(f"/api/jobs/{sample_job.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_job.id)
        assert data["status"] == "pending"
        assert data["instruction"] == "Make the header blue"

    def test_get_nonexistent(self, client):
        response = client.get(f"/api/jobs/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_with_proposals(self, client, analyzed_job):
        response = client.get(f"/api/jobs/{analyzed_job.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "analyzed"
        assert len(data["proposals"]) == 2
        assert data["proposals"][0]["title"] == "Proposal 0"
        assert data["proposals"][0]["plan"] == ["step 1"]
        assert data["proposals"][0]["files"] == [{"path": "src/App.tsx"}]


class TestCreateJob:
    def test_create_success(self, client, monkeypatch):
        # Mock the asyncio.create_task to avoid launching background analysis
        import app.usecase.job_usecase as usecase_mod

        monkeypatch.setattr(usecase_mod.asyncio, "create_task", lambda coro: coro.close())

        response = client.post(
            "/api/jobs/",
            json={
                "repo_url": "https://github.com/new/repo",
                "branch": "develop",
                "instruction": "Add dark mode",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["repo_url"] == "https://github.com/new/repo"
        assert data["branch"] == "develop"
        assert data["status"] == "pending"

    def test_create_missing_fields(self, client):
        response = client.post("/api/jobs/", json={})
        assert response.status_code == 422

    def test_create_empty_instruction(self, client):
        response = client.post(
            "/api/jobs/",
            json={"repo_url": "https://github.com/test/repo", "instruction": ""},
        )
        assert response.status_code == 422


class TestGetScreenshot:
    def test_before_screenshot_not_found(self, client, sample_job):
        response = client.get(f"/api/jobs/{sample_job.id}/screenshot/before")
        assert response.status_code == 404

    def test_after_screenshot_not_found(self, client, sample_job):
        response = client.get(f"/api/jobs/{sample_job.id}/proposals/0/screenshot")
        assert response.status_code == 404


class TestGetDiff:
    def test_diff_not_found(self, client, sample_job):
        response = client.get(f"/api/jobs/{sample_job.id}/proposals/0/diff")
        assert response.status_code == 404


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
