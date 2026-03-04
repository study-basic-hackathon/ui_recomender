"""Unit tests for session usecases using mock repositories (no DB required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.model.session import (
    Iteration,
    IterationStatus,
    Proposal,
    ProposalStatus,
    Session,
    SessionStatus,
)
from app.repository.mock import (
    MockIterationRepository,
    MockProposalRepository,
    MockSessionRepository,
)
from app.usecase.session_usecase import (
    CreateSessionPRUseCase,
    CreateSessionUseCase,
    IterateUseCase,
)

# ── Helpers ──


def _make_session(
    status: SessionStatus = SessionStatus.ACTIVE,
) -> Session:
    return Session(
        id=uuid4(),
        repo_url="https://github.com/test/repo",
        base_branch="main",
        status=status,
    )


def _make_iteration(
    session_id: UUID,
    *,
    index: int = 0,
    status: IterationStatus = IterationStatus.COMPLETED,
    version: int = 1,
) -> Iteration:
    return Iteration(
        id=uuid4(),
        session_id=session_id,
        iteration_index=index,
        instruction="test instruction",
        status=status,
        version=version,
    )


def _make_proposal(
    iteration_id: UUID,
    *,
    index: int = 0,
    status: ProposalStatus = ProposalStatus.COMPLETED,
    version: int = 1,
    pr_status: str | None = None,
) -> Proposal:
    return Proposal(
        id=uuid4(),
        iteration_id=iteration_id,
        proposal_index=index,
        title=f"Proposal {index}",
        concept="test concept",
        plan="[]",
        files="[]",
        complexity="medium",
        status=status,
        pr_status=pr_status,
        version=version,
    )


# ── IterateUseCase tests ──


class TestIterateUseCase:
    def _build(
        self,
        session_repo: MockSessionRepository | None = None,
        iteration_repo: MockIterationRepository | None = None,
        proposal_repo: MockProposalRepository | None = None,
        s3_client: MagicMock | None = None,
    ) -> IterateUseCase:
        return IterateUseCase(
            db=MagicMock(),
            session_repo=session_repo or MockSessionRepository(),
            iteration_repo=iteration_repo or MockIterationRepository(),
            proposal_repo=proposal_repo or MockProposalRepository(),
            s3_client=s3_client,
        )

    @pytest.mark.asyncio
    async def test_session_not_found(self) -> None:
        uc = self._build()
        with pytest.raises(ValueError, match="Session not found"):
            await uc.execute(uuid4(), 0, "instruction")

    @pytest.mark.asyncio
    async def test_session_not_active(self) -> None:
        sr = MockSessionRepository()
        session = _make_session(status=SessionStatus.COMPLETED)
        sr.create(session)

        uc = self._build(session_repo=sr)
        with pytest.raises(ValueError, match="Session is not active"):
            await uc.execute(session.id, 0, "instruction")

    @pytest.mark.asyncio
    async def test_no_iterations_found(self) -> None:
        sr = MockSessionRepository()
        session = _make_session()
        sr.create(session)

        uc = self._build(session_repo=sr)
        with pytest.raises(ValueError, match="No iterations found"):
            await uc.execute(session.id, 0, "instruction")

    @pytest.mark.asyncio
    async def test_previous_iteration_not_completed(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, status=IterationStatus.ANALYZING)
        ir.create(iteration)

        uc = self._build(session_repo=sr, iteration_repo=ir)
        with pytest.raises(ValueError, match="Previous iteration is not completed"):
            await uc.execute(session.id, 0, "instruction")

    @pytest.mark.asyncio
    async def test_proposal_not_found(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id)
        ir.create(iteration)

        uc = self._build(session_repo=sr, iteration_repo=ir)
        with pytest.raises(ValueError, match="Proposal 0 not found"):
            await uc.execute(session.id, 0, "instruction")

    @pytest.mark.asyncio
    async def test_proposal_not_completed(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id)
        ir.create(iteration)
        proposal = _make_proposal(
            iteration.id, status=ProposalStatus.IMPLEMENTING
        )
        pr.create(proposal)

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr)
        with pytest.raises(ValueError, match="Proposal is not completed"):
            await uc.execute(session.id, 0, "instruction")

    @pytest.mark.asyncio
    async def test_no_patch_in_s3(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id)
        ir.create(iteration)
        proposal = _make_proposal(iteration.id)
        pr.create(proposal)

        s3 = MagicMock()
        s3.exists.return_value = False

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr, s3_client=s3)
        with pytest.raises(ValueError, match="No patch file found"):
            await uc.execute(session.id, 0, "instruction")

    @pytest.mark.asyncio
    @patch("app.usecase.session_usecase.asyncio.create_task")
    async def test_happy_path(self, mock_create_task: MagicMock) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, index=0)
        ir.create(iteration)
        proposal = _make_proposal(iteration.id, index=0)
        pr.create(proposal)

        s3 = MagicMock()
        s3.exists.return_value = True

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr, s3_client=s3)
        result = await uc.execute(session.id, 0, "next instruction")

        assert result.id == session.id
        # selected_proposal set on previous iteration
        assert iteration.selected_proposal_index == 0
        # new iteration created
        new_iter = ir.get_by_session_and_index(session.id, 1)
        assert new_iter is not None
        assert new_iter.status == IterationStatus.PENDING
        assert new_iter.instruction == "next instruction"
        # background task launched
        mock_create_task.assert_called_once()


# ── CreateSessionPRUseCase tests ──


class TestCreateSessionPRUseCase:
    def _build(
        self,
        session_repo: MockSessionRepository | None = None,
        iteration_repo: MockIterationRepository | None = None,
        proposal_repo: MockProposalRepository | None = None,
    ) -> CreateSessionPRUseCase:
        return CreateSessionPRUseCase(
            db=MagicMock(),
            session_repo=session_repo or MockSessionRepository(),
            iteration_repo=iteration_repo or MockIterationRepository(),
            proposal_repo=proposal_repo or MockProposalRepository(),
        )

    @pytest.mark.asyncio
    async def test_session_not_found(self) -> None:
        uc = self._build()
        with pytest.raises(ValueError, match="Session not found"):
            await uc.execute(uuid4(), 0, 0)

    @pytest.mark.asyncio
    async def test_iteration_not_found(self) -> None:
        sr = MockSessionRepository()
        session = _make_session()
        sr.create(session)

        uc = self._build(session_repo=sr)
        with pytest.raises(ValueError, match="Iteration 0 not found"):
            await uc.execute(session.id, 0, 0)

    @pytest.mark.asyncio
    async def test_proposal_not_found(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, index=0)
        ir.create(iteration)

        uc = self._build(session_repo=sr, iteration_repo=ir)
        with pytest.raises(ValueError, match="Proposal 0 not found"):
            await uc.execute(session.id, 0, 0)

    @pytest.mark.asyncio
    async def test_proposal_not_completed(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, index=0)
        ir.create(iteration)
        proposal = _make_proposal(
            iteration.id, status=ProposalStatus.IMPLEMENTING
        )
        pr.create(proposal)

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr)
        with pytest.raises(ValueError, match="Proposal is not completed"):
            await uc.execute(session.id, 0, 0)

    @pytest.mark.asyncio
    async def test_pr_already_created(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, index=0)
        ir.create(iteration)
        proposal = _make_proposal(iteration.id, pr_status="created")
        pr.create(proposal)

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr)
        with pytest.raises(ValueError, match="PR already created"):
            await uc.execute(session.id, 0, 0)

    @pytest.mark.asyncio
    async def test_pr_creation_in_progress(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, index=0)
        ir.create(iteration)
        proposal = _make_proposal(iteration.id, pr_status="creating")
        pr.create(proposal)

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr)
        with pytest.raises(ValueError, match="PR creation already in progress"):
            await uc.execute(session.id, 0, 0)

    @pytest.mark.asyncio
    async def test_concurrent_update_detected(self) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, index=0)
        ir.create(iteration)
        proposal = _make_proposal(iteration.id, version=1)
        pr.create(proposal)

        # Wrap update_status_optimistic to always return None (simulating race)
        pr.update_status_optimistic = lambda *a, **kw: None  # type: ignore[method-assign]

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr)
        with pytest.raises(ValueError, match="Concurrent update detected"):
            await uc.execute(session.id, 0, 0)

    @pytest.mark.asyncio
    @patch("app.usecase.session_usecase.asyncio.create_task")
    async def test_happy_path(self, mock_create_task: MagicMock) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        pr = MockProposalRepository()

        session = _make_session()
        sr.create(session)
        iteration = _make_iteration(session.id, index=0)
        ir.create(iteration)
        proposal = _make_proposal(iteration.id, version=1)
        pr.create(proposal)

        uc = self._build(session_repo=sr, iteration_repo=ir, proposal_repo=pr)
        result = await uc.execute(session.id, 0, 0)

        # Optimistic lock succeeded → pr_status updated
        assert result.pr_status == "creating"
        assert result.version == 2
        # background task launched
        mock_create_task.assert_called_once()


# ── CreateSessionUseCase tests ──


class TestCreateSessionUseCase:
    @pytest.mark.asyncio
    @patch("app.usecase.session_usecase.asyncio.create_task")
    async def test_creates_session_and_iteration(self, mock_create_task: MagicMock) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        s3 = MagicMock()

        uc = CreateSessionUseCase(
            db=MagicMock(),
            session_repo=sr,
            iteration_repo=ir,
            s3_client=s3,
        )
        result = await uc.execute(
            repo_url="https://github.com/test/repo",
            branch="main",
            instruction="do something",
        )

        # Session created
        assert result.repo_url == "https://github.com/test/repo"
        assert result.status == SessionStatus.ACTIVE

        # Iteration 0 created
        iterations = ir.get_all_for_session(result.id)
        assert len(iterations) == 1
        assert iterations[0].iteration_index == 0
        assert iterations[0].instruction == "do something"

        # S3 bucket ensured
        s3._ensure_bucket.assert_called_once()

        # background task launched
        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.usecase.session_usecase.asyncio.create_task")
    async def test_iteration_defaults(self, mock_create_task: MagicMock) -> None:
        sr = MockSessionRepository()
        ir = MockIterationRepository()
        s3 = MagicMock()

        uc = CreateSessionUseCase(
            db=MagicMock(),
            session_repo=sr,
            iteration_repo=ir,
            s3_client=s3,
        )
        result = await uc.execute(
            repo_url="https://github.com/test/repo",
            branch="main",
            instruction="test",
        )

        iteration = ir.get_latest_for_session(result.id)
        assert iteration is not None
        assert iteration.status == IterationStatus.PENDING
        assert iteration.iteration_index == 0
