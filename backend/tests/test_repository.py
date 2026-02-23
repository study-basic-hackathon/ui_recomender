import uuid

from app.model.job import Job, JobStatus, Proposal, ProposalStatus
from app.repository.job_repository import JobRepository
from app.repository.proposal_repository import ProposalRepository
from app.repository.setting_repository import SettingRepository


class TestJobRepository:
    def test_create_and_get(self, db):
        repo = JobRepository(db)
        job = Job(
            repo_url="https://github.com/test/repo",
            branch="main",
            instruction="Fix the button color",
        )
        created = repo.create(job)

        assert created.id is not None
        assert created.status == JobStatus.PENDING

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.repo_url == "https://github.com/test/repo"

    def test_get_by_id_not_found(self, db):
        repo = JobRepository(db)
        result = repo.get_by_id(uuid.uuid4())
        assert result is None

    def test_update_status(self, db):
        repo = JobRepository(db)
        job = repo.create(
            Job(
                repo_url="https://github.com/test/repo",
                branch="main",
                instruction="Update layout",
            )
        )

        updated = repo.update_status(job.id, JobStatus.ANALYZING, k8s_job_name="test-job")
        assert updated is not None
        assert updated.status == JobStatus.ANALYZING
        assert updated.k8s_job_name == "test-job"

    def test_update_status_with_error(self, db):
        repo = JobRepository(db)
        job = repo.create(
            Job(
                repo_url="https://github.com/test/repo",
                branch="main",
                instruction="Update layout",
            )
        )

        updated = repo.update_status(job.id, JobStatus.FAILED, error_message="Something went wrong")
        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert updated.error_message == "Something went wrong"

    def test_list_all(self, db):
        repo = JobRepository(db)
        repo.create(
            Job(
                repo_url="https://github.com/test/a",
                branch="main",
                instruction="A",
            )
        )
        repo.create(
            Job(
                repo_url="https://github.com/test/b",
                branch="main",
                instruction="B",
            )
        )

        jobs = repo.list_all()
        assert len(jobs) >= 2


class TestProposalRepository:
    def _create_job(self, db) -> Job:
        repo = JobRepository(db)
        return repo.create(
            Job(
                repo_url="https://github.com/test/repo",
                branch="main",
                instruction="Test",
            )
        )

    def test_create_and_get(self, db):
        job = self._create_job(db)
        repo = ProposalRepository(db)
        proposal = repo.create(
            Proposal(
                job_id=job.id,
                proposal_index=0,
                title="Modern Layout",
                concept="A clean modern layout",
                plan='["step 1", "step 2"]',
            )
        )

        assert proposal.id is not None
        assert proposal.status == ProposalStatus.PENDING

        fetched = repo.get_by_id(proposal.id)
        assert fetched is not None
        assert fetched.title == "Modern Layout"

    def test_get_by_job_and_index(self, db):
        job = self._create_job(db)
        repo = ProposalRepository(db)
        repo.create(
            Proposal(
                job_id=job.id,
                proposal_index=0,
                title="Proposal A",
                concept="A",
                plan="[]",
            )
        )
        repo.create(
            Proposal(
                job_id=job.id,
                proposal_index=1,
                title="Proposal B",
                concept="B",
                plan="[]",
            )
        )

        result = repo.get_by_job_and_index(job.id, 1)
        assert result is not None
        assert result.title == "Proposal B"

        result = repo.get_by_job_and_index(job.id, 99)
        assert result is None

    def test_get_all_for_job(self, db):
        job = self._create_job(db)
        repo = ProposalRepository(db)
        for i in range(3):
            repo.create(
                Proposal(
                    job_id=job.id,
                    proposal_index=i,
                    title=f"Proposal {i}",
                    concept=f"Concept {i}",
                    plan="[]",
                )
            )

        proposals = repo.get_all_for_job(job.id)
        assert len(proposals) == 3
        assert proposals[0].proposal_index == 0
        assert proposals[2].proposal_index == 2

    def test_update_status(self, db):
        job = self._create_job(db)
        repo = ProposalRepository(db)
        proposal = repo.create(
            Proposal(
                job_id=job.id,
                proposal_index=0,
                title="Test",
                concept="Test",
                plan="[]",
            )
        )

        updated = repo.update_status(proposal.id, ProposalStatus.COMPLETED)
        assert updated is not None
        assert updated.status == ProposalStatus.COMPLETED


class TestSettingRepository:
    def test_upsert_create(self, db):
        repo = SettingRepository(db)
        setting = repo.upsert("theme", "dark")
        assert setting.key == "theme"
        assert setting.value == "dark"

    def test_upsert_update(self, db):
        repo = SettingRepository(db)
        repo.upsert("theme", "dark")
        updated = repo.upsert("theme", "light")
        assert updated.value == "light"

    def test_get_by_key(self, db):
        repo = SettingRepository(db)
        repo.upsert("api_key", "test-key")

        setting = repo.get_by_key("api_key")
        assert setting is not None
        assert setting.value == "test-key"

        assert repo.get_by_key("nonexistent") is None

    def test_list_all(self, db):
        repo = SettingRepository(db)
        repo.upsert("a", "1")
        repo.upsert("b", "2")

        settings = repo.list_all()
        assert len(settings) >= 2

    def test_delete(self, db):
        repo = SettingRepository(db)
        repo.upsert("to_delete", "value")
        assert repo.delete("to_delete") is True
        assert repo.get_by_key("to_delete") is None
        assert repo.delete("nonexistent") is False
