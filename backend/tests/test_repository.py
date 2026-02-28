import uuid

from app.model.session import (
    Iteration,
    IterationStatus,
    Proposal,
    ProposalStatus,
    Session,
    SessionStatus,
)
from app.repository.iteration_repository import IterationRepository
from app.repository.proposal_repository import ProposalRepository
from app.repository.session_repository import SessionRepository
from app.repository.setting_repository import SettingRepository


class TestSessionRepository:
    def test_create_and_get(self, db):
        repo = SessionRepository(db)
        session = Session(
            repo_url="https://github.com/test/repo",
            base_branch="main",
        )
        created = repo.create(session)

        assert created.id is not None
        assert created.status == SessionStatus.ACTIVE

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.repo_url == "https://github.com/test/repo"

    def test_get_by_id_not_found(self, db):
        repo = SessionRepository(db)
        result = repo.get_by_id(uuid.uuid4())
        assert result is None

    def test_list_all(self, db):
        repo = SessionRepository(db)
        repo.create(Session(repo_url="https://github.com/test/a", base_branch="main"))
        repo.create(Session(repo_url="https://github.com/test/b", base_branch="main"))

        sessions = repo.list_all()
        assert len(sessions) >= 2


class TestIterationRepository:
    def _create_session(self, db) -> Session:
        repo = SessionRepository(db)
        return repo.create(
            Session(repo_url="https://github.com/test/repo", base_branch="main")
        )

    def test_create_and_get(self, db):
        session = self._create_session(db)
        repo = IterationRepository(db)
        iteration = repo.create(
            Iteration(
                session_id=session.id,
                iteration_index=0,
                instruction="Make button blue",
            )
        )

        assert iteration.id is not None
        assert iteration.status == IterationStatus.PENDING

        fetched = repo.get_by_id(iteration.id)
        assert fetched is not None
        assert fetched.instruction == "Make button blue"

    def test_get_latest_for_session(self, db):
        session = self._create_session(db)
        repo = IterationRepository(db)
        repo.create(
            Iteration(session_id=session.id, iteration_index=0, instruction="First")
        )
        repo.create(
            Iteration(session_id=session.id, iteration_index=1, instruction="Second")
        )

        latest = repo.get_latest_for_session(session.id)
        assert latest is not None
        assert latest.iteration_index == 1
        assert latest.instruction == "Second"


class TestProposalRepository:
    def _create_iteration(self, db) -> Iteration:
        session_repo = SessionRepository(db)
        session = session_repo.create(
            Session(repo_url="https://github.com/test/repo", base_branch="main")
        )
        iter_repo = IterationRepository(db)
        return iter_repo.create(
            Iteration(
                session_id=session.id, iteration_index=0, instruction="Test"
            )
        )

    def test_create_and_get(self, db):
        iteration = self._create_iteration(db)
        repo = ProposalRepository(db)
        proposal = repo.create(
            Proposal(
                iteration_id=iteration.id,
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

    def test_get_by_iteration_and_index(self, db):
        iteration = self._create_iteration(db)
        repo = ProposalRepository(db)
        repo.create(
            Proposal(
                iteration_id=iteration.id,
                proposal_index=0,
                title="Proposal A",
                concept="A",
                plan="[]",
            )
        )
        repo.create(
            Proposal(
                iteration_id=iteration.id,
                proposal_index=1,
                title="Proposal B",
                concept="B",
                plan="[]",
            )
        )

        result = repo.get_by_iteration_and_index(iteration.id, 1)
        assert result is not None
        assert result.title == "Proposal B"

        result = repo.get_by_iteration_and_index(iteration.id, 99)
        assert result is None

    def test_get_all_for_iteration(self, db):
        iteration = self._create_iteration(db)
        repo = ProposalRepository(db)
        for i in range(3):
            repo.create(
                Proposal(
                    iteration_id=iteration.id,
                    proposal_index=i,
                    title=f"Proposal {i}",
                    concept=f"Concept {i}",
                    plan="[]",
                )
            )

        proposals = repo.get_all_for_iteration(iteration.id)
        assert len(proposals) == 3
        assert proposals[0].proposal_index == 0
        assert proposals[2].proposal_index == 2

    def test_update_status_optimistic(self, db):
        iteration = self._create_iteration(db)
        repo = ProposalRepository(db)
        proposal = repo.create(
            Proposal(
                iteration_id=iteration.id,
                proposal_index=0,
                title="Test",
                concept="Test",
                plan="[]",
            )
        )

        updated = repo.update_status_optimistic(
            proposal.id, proposal.version, ProposalStatus.COMPLETED
        )
        assert updated is not None
        assert updated.status == ProposalStatus.COMPLETED
        assert updated.version == 2


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
