import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.infra.s3_client import S3Client
from app.model.session import (
    Iteration,
    IterationStatus,
    Proposal,
    ProposalStatus,
    Session,
    SessionStatus,
)
from app.repository.database import SessionLocal
from app.repository.iteration_repository import IterationRepository
from app.repository.proposal_repository import ProposalRepository
from app.repository.protocols import (
    IterationRepositoryProtocol,
    ProposalRepositoryProtocol,
    SessionRepositoryProtocol,
)
from app.repository.session_repository import SessionRepository
from app.workflow.session_analyzer_graph import build_session_analyzer_graph
from app.workflow.session_create_pr_graph import build_session_create_pr_graph
from app.workflow.session_implementation_graph import build_session_implementation_graph

logger = logging.getLogger(__name__)


def _update_iteration_status_with_retry(
    iter_repo: IterationRepository,
    iteration_id: UUID,
    new_status: IterationStatus,
    max_retries: int = 3,
    **kwargs: object,
) -> Iteration | None:
    """Update iteration status with retry on version mismatch."""
    for attempt in range(max_retries):
        iteration = iter_repo.get_by_id(iteration_id)
        if not iteration:
            return None
        result = iter_repo.update_status_optimistic(
            iteration_id, iteration.version, new_status, **kwargs
        )
        if result:
            return result
        logger.warning(
            "Iteration %s status update to %s failed (attempt %d), retrying...",
            iteration_id,
            new_status,
            attempt + 1,
        )
    logger.error(
        "Failed to update iteration %s to %s after %d retries",
        iteration_id,
        new_status,
        max_retries,
    )
    return None


class CreateSessionUseCase:
    """Create a new session and trigger the first analysis."""

    def __init__(
        self,
        db: DbSession,
        session_repo: SessionRepositoryProtocol | None = None,
        iteration_repo: IterationRepositoryProtocol | None = None,
        s3_client: S3Client | None = None,
    ) -> None:
        self.db = db
        self.session_repo = session_repo or SessionRepository(db)
        self.iteration_repo = iteration_repo or IterationRepository(db)
        self.s3_client = s3_client

    async def execute(self, repo_url: str, branch: str, instruction: str) -> Session:
        # Create session
        session = Session(
            repo_url=repo_url,
            base_branch=branch,
            status=SessionStatus.ACTIVE,
        )
        session = self.session_repo.create(session)
        session_id = str(session.id)

        # Create iteration 0
        iteration = Iteration(
            session_id=session.id,
            iteration_index=0,
            instruction=instruction,
            status=IterationStatus.PENDING,
        )
        iteration = self.iteration_repo.create(iteration)

        # Ensure S3 bucket exists
        s3 = self.s3_client or S3Client()
        s3._ensure_bucket()

        # Run analysis in background
        asyncio.create_task(
            _run_session_analysis(
                session_id=session_id,
                iteration_id=str(iteration.id),
                iteration_index=0,
                repo_url=repo_url,
                branch=branch,
                instruction=instruction,
                selected_proposal_index=None,
            )
        )

        return session


class IterateUseCase:
    """Create the next iteration in a session."""

    def __init__(
        self,
        db: DbSession,
        session_repo: SessionRepositoryProtocol | None = None,
        iteration_repo: IterationRepositoryProtocol | None = None,
        proposal_repo: ProposalRepositoryProtocol | None = None,
        s3_client: S3Client | None = None,
    ) -> None:
        self.db = db
        self.session_repo = session_repo or SessionRepository(db)
        self.iteration_repo = iteration_repo or IterationRepository(db)
        self.proposal_repo = proposal_repo or ProposalRepository(db)
        self.s3_client = s3_client

    async def execute(
        self, session_id: UUID, selected_proposal_index: int, instruction: str
    ) -> Session:
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError("Session not found")
        if session.status != SessionStatus.ACTIVE:
            raise ValueError(f"Session is not active: {session.status}")

        # Validate the previous iteration is completed
        latest = self.iteration_repo.get_latest_for_session(session_id)
        if not latest:
            raise ValueError("No iterations found")
        if latest.status != IterationStatus.COMPLETED:
            raise ValueError(f"Previous iteration is not completed: {latest.status}")

        # Validate the selected proposal exists and is completed
        proposal = self.proposal_repo.get_by_iteration_and_index(latest.id, selected_proposal_index)
        if not proposal:
            raise ValueError(f"Proposal {selected_proposal_index} not found")
        if proposal.status != ProposalStatus.COMPLETED:
            raise ValueError(f"Proposal is not completed: {proposal.status}")

        # Verify the patch exists in S3
        s3 = self.s3_client or S3Client()
        diff_k = s3.diff_key(str(session_id), latest.iteration_index, selected_proposal_index)
        if not s3.exists(diff_k):
            raise ValueError("No patch file found for the selected proposal")

        # Mark selected proposal on previous iteration
        self.iteration_repo.update_selected_proposal(latest.id, selected_proposal_index)

        # Create new iteration
        new_index = latest.iteration_index + 1
        iteration = Iteration(
            session_id=session_id,
            iteration_index=new_index,
            instruction=instruction,
            status=IterationStatus.PENDING,
        )
        try:
            iteration = self.iteration_repo.create(iteration)
        except IntegrityError:
            self.db.rollback()
            # Idempotency: return existing iteration
            existing = self.iteration_repo.get_by_session_and_index(session_id, new_index)
            if existing:
                session = self.session_repo.get_by_id(session_id)
                if not session:
                    raise ValueError("Session not found") from None
                return session
            raise

        # Run analysis in background
        asyncio.create_task(
            _run_session_analysis(
                session_id=str(session_id),
                iteration_id=str(iteration.id),
                iteration_index=new_index,
                repo_url=str(session.repo_url),
                branch=str(session.base_branch),
                instruction=instruction,
                selected_proposal_index=selected_proposal_index,
            )
        )

        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError("Session not found")
        return session


class CreateSessionPRUseCase:
    """Create a PR from a specific proposal in a session."""

    def __init__(
        self,
        db: DbSession,
        session_repo: SessionRepositoryProtocol | None = None,
        iteration_repo: IterationRepositoryProtocol | None = None,
        proposal_repo: ProposalRepositoryProtocol | None = None,
    ) -> None:
        self.db = db
        self.session_repo = session_repo or SessionRepository(db)
        self.iteration_repo = iteration_repo or IterationRepository(db)
        self.proposal_repo = proposal_repo or ProposalRepository(db)

    async def execute(
        self, session_id: UUID, iteration_index: int, proposal_index: int
    ) -> Proposal:
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError("Session not found")

        iteration = self.iteration_repo.get_by_session_and_index(session_id, iteration_index)
        if not iteration:
            raise ValueError(f"Iteration {iteration_index} not found")

        proposal = self.proposal_repo.get_by_iteration_and_index(iteration.id, proposal_index)
        if not proposal:
            raise ValueError(f"Proposal {proposal_index} not found")
        if proposal.status != ProposalStatus.COMPLETED:
            raise ValueError(f"Proposal is not completed: {proposal.status}")
        if proposal.pr_status == "created":
            raise ValueError("PR already created")
        if proposal.pr_status == "creating":
            raise ValueError("PR creation already in progress")

        # Optimistic lock: update pr_status
        updated = self.proposal_repo.update_status_optimistic(
            proposal.id,
            proposal.version,
            ProposalStatus.COMPLETED,
            pr_status="creating",
        )
        if not updated:
            raise ValueError("Concurrent update detected")

        asyncio.create_task(
            _run_session_create_pr(
                session_id=str(session_id),
                iteration_index=iteration_index,
                repo_url=str(session.repo_url),
                branch=str(session.base_branch),
                proposal_index=proposal_index,
                proposal_id=str(proposal.id),
            )
        )

        return updated


# ── Background tasks (static, use own DB sessions) ──


async def _run_session_analysis(
    session_id: str,
    iteration_id: str,
    iteration_index: int,
    repo_url: str,
    branch: str,
    instruction: str,
    selected_proposal_index: int | None,
) -> None:
    """Background: run session analyzer workflow, then auto-implement all proposals."""
    db = SessionLocal()
    iter_repo = IterationRepository(db)
    proposal_repo = ProposalRepository(db)
    try:
        iteration = iter_repo.get_by_id(UUID(iteration_id))
        if not iteration:
            logger.error("Iteration %s not found", iteration_id)
            return

        _update_iteration_status_with_retry(
            iter_repo, UUID(iteration_id), IterationStatus.ANALYZING
        )

        graph = build_session_analyzer_graph()
        result = await graph.ainvoke(
            {
                "session_id": session_id,
                "iteration_index": iteration_index,
                "repo_url": repo_url,
                "branch": branch,
                "instruction": instruction,
                "num_proposals": get_settings().MAX_PROPOSALS,
                "selected_proposal_index": selected_proposal_index,
                "k8s_job_name": None,
                "status": "pending",
                "error": None,
                "proposals": None,
                "before_screenshot_key": None,
                "device_type": None,
            }
        )

        if result.get("proposals"):
            device_type = result.get("device_type", "desktop")
            proposals = []
            for i, prop in enumerate(result["proposals"]):
                p = Proposal(
                    iteration_id=UUID(iteration_id),
                    proposal_index=i,
                    title=prop.get("title", f"Proposal {i + 1}"),
                    concept=prop.get("concept", ""),
                    plan=json.dumps(prop.get("plan", []), ensure_ascii=False),
                    files=json.dumps(prop.get("files", []), ensure_ascii=False),
                    complexity=prop.get("complexity", "medium"),
                    status=ProposalStatus.PENDING,
                )
                proposals.append(proposal_repo.create(p))

            _update_iteration_status_with_retry(
                iter_repo,
                UUID(iteration_id),
                IterationStatus.ANALYZED,
                before_screenshot_key=result.get("before_screenshot_key"),
                device_type=device_type,
            )
            logger.info(
                "Session %s iter %d analysis done: %d proposals (device: %s)",
                session_id,
                iteration_index,
                len(proposals),
                device_type,
            )

            # Auto-trigger implementation for ALL proposals
            _update_iteration_status_with_retry(
                iter_repo, UUID(iteration_id), IterationStatus.IMPLEMENTING
            )
            for proposal in proposals:
                asyncio.create_task(
                    _run_session_implementation(
                        session_id=session_id,
                        iteration_id=iteration_id,
                        iteration_index=iteration_index,
                        repo_url=repo_url,
                        branch=branch,
                        proposal_index=proposal.proposal_index,
                        proposal_id=str(proposal.id),
                        plan_json=str(proposal.plan),
                        selected_proposal_index=selected_proposal_index,
                        device_type=device_type,
                    )
                )
        else:
            error = result.get("error", "No proposals generated")
            _update_iteration_status_with_retry(
                iter_repo,
                UUID(iteration_id),
                IterationStatus.FAILED,
                error_message=error,
            )
            logger.warning(
                "Session %s iter %d analysis failed: %s", session_id, iteration_index, error
            )

    except Exception:
        logger.exception("Session %s iter %d analysis failed", session_id, iteration_index)
        try:
            _update_iteration_status_with_retry(
                iter_repo,
                UUID(iteration_id),
                IterationStatus.FAILED,
                error_message="Internal error during analysis",
            )
        except Exception:
            logger.exception("Failed to update iteration status")
    finally:
        db.close()


async def _run_session_implementation(
    session_id: str,
    iteration_id: str,
    iteration_index: int,
    repo_url: str,
    branch: str,
    proposal_index: int,
    proposal_id: str,
    plan_json: str,
    selected_proposal_index: int | None,
    device_type: str = "desktop",
) -> None:
    """Background: run one session-based implementation workflow."""
    db = SessionLocal()
    proposal_repo = ProposalRepository(db)
    try:
        proposal = proposal_repo.get_by_id(UUID(proposal_id))
        if not proposal:
            logger.error("Proposal %s not found", proposal_id)
            return

        proposal_repo.update_status_optimistic(
            UUID(proposal_id), proposal.version, ProposalStatus.IMPLEMENTING
        )

        graph = build_session_implementation_graph()
        result = await graph.ainvoke(
            {
                "session_id": session_id,
                "iteration_index": iteration_index,
                "repo_url": repo_url,
                "branch": branch,
                "proposal_index": proposal_index,
                "proposal_plan": plan_json,
                "device_type": device_type,
                "selected_proposal_index": selected_proposal_index,
                "k8s_job_name": None,
                "status": "pending",
                "error": None,
                "after_screenshot_key": None,
                "diff_key": None,
            }
        )

        if result.get("status") == "succeeded" or result.get("after_screenshot_key"):
            proposal = proposal_repo.get_by_id(UUID(proposal_id))
            if proposal:
                proposal_repo.update_status_optimistic(
                    UUID(proposal_id),
                    proposal.version,
                    ProposalStatus.COMPLETED,
                    after_screenshot_key=result.get("after_screenshot_key"),
                    diff_key=result.get("diff_key"),
                )
            logger.info(
                "Session %s iter %d proposal %d implementation done",
                session_id,
                iteration_index,
                proposal_index,
            )
        else:
            error = result.get("error", "Implementation failed")
            proposal = proposal_repo.get_by_id(UUID(proposal_id))
            if proposal:
                proposal_repo.update_status_optimistic(
                    UUID(proposal_id),
                    proposal.version,
                    ProposalStatus.FAILED,
                    error_message=error,
                )

        _check_iteration_completion(db, UUID(iteration_id))

    except Exception:
        logger.exception(
            "Session %s iter %d proposal %d implementation failed",
            session_id,
            iteration_index,
            proposal_index,
        )
        try:
            proposal = proposal_repo.get_by_id(UUID(proposal_id))
            if proposal:
                proposal_repo.update_status_optimistic(
                    UUID(proposal_id),
                    proposal.version,
                    ProposalStatus.FAILED,
                    error_message="Internal error during implementation",
                )
            _check_iteration_completion(db, UUID(iteration_id))
        except Exception:
            logger.exception("Failed to update proposal status")
    finally:
        db.close()


async def _run_session_create_pr(
    session_id: str,
    iteration_index: int,
    repo_url: str,
    branch: str,
    proposal_index: int,
    proposal_id: str,
) -> None:
    """Background: run session-based PR creation workflow."""
    db = SessionLocal()
    proposal_repo = ProposalRepository(db)
    try:
        graph = build_session_create_pr_graph()
        result = await graph.ainvoke(
            {
                "session_id": session_id,
                "iteration_index": iteration_index,
                "repo_url": repo_url,
                "branch": branch,
                "proposal_index": proposal_index,
                "k8s_job_name": None,
                "status": "pending",
                "error": None,
                "pr_url": None,
            }
        )

        proposal = proposal_repo.get_by_id(UUID(proposal_id))
        if not proposal:
            return

        if result.get("pr_url"):
            proposal_repo.update_status_optimistic(
                UUID(proposal_id),
                proposal.version,
                ProposalStatus.COMPLETED,
                pr_url=result["pr_url"],
                pr_status="created",
            )
            logger.info("PR created for session %s: %s", session_id, result["pr_url"])
        else:
            error = result.get("error", "PR creation failed")
            proposal_repo.update_status_optimistic(
                UUID(proposal_id),
                proposal.version,
                ProposalStatus.COMPLETED,
                pr_status="failed",
                error_message=error,
            )

    except Exception:
        logger.exception("PR creation failed for session %s", session_id)
        try:
            proposal = proposal_repo.get_by_id(UUID(proposal_id))
            if proposal:
                proposal_repo.update_status_optimistic(
                    UUID(proposal_id),
                    proposal.version,
                    ProposalStatus.COMPLETED,
                    pr_status="failed",
                    error_message="Internal error during PR creation",
                )
        except Exception:
            logger.exception("Failed to update proposal PR status")
    finally:
        db.close()


async def recover_stuck_proposals() -> None:
    """Recover proposals stuck in IMPLEMENTING status by checking S3 for results.

    Called on app startup to handle cases where the app restarted while
    background implementation tasks were polling K8s jobs.
    """
    db = SessionLocal()
    try:
        proposal_repo = ProposalRepository(db)
        iter_repo = IterationRepository(db)
        s3 = S3Client()

        stuck = proposal_repo.get_all_by_status(ProposalStatus.IMPLEMENTING)
        if not stuck:
            logger.info("No stuck proposals found")
            return

        logger.info("Found %d stuck proposals, attempting recovery...", len(stuck))
        recovered = 0
        for proposal in stuck:
            iteration = iter_repo.get_by_id(proposal.iteration_id)
            if not iteration:
                continue
            session_id = str(iteration.session_id)
            iter_idx = iteration.iteration_index
            prop_idx = proposal.proposal_index

            after_key = s3.after_screenshot_key(session_id, iter_idx, prop_idx)
            diff_k = s3.diff_key(session_id, iter_idx, prop_idx)
            has_after = s3.exists(after_key)
            has_diff = s3.exists(diff_k)

            if has_diff:
                proposal_repo.update_status_optimistic(
                    proposal.id,
                    proposal.version,
                    ProposalStatus.COMPLETED,
                    after_screenshot_key=after_key if has_after else None,
                    diff_key=diff_k,
                )
                recovered += 1
                logger.info(
                    "Recovered proposal %s (iter%d/prop%d)",
                    proposal.id,
                    iter_idx,
                    prop_idx,
                )

        # Check iteration completion for affected iterations
        seen_iterations: set[UUID] = set()
        for proposal in stuck:
            if proposal.iteration_id not in seen_iterations:
                seen_iterations.add(proposal.iteration_id)
                _check_iteration_completion(db, proposal.iteration_id)

        logger.info("Recovery complete: %d/%d proposals recovered", recovered, len(stuck))
    except Exception:
        logger.exception("Error during stuck proposal recovery")
    finally:
        db.close()


def _check_iteration_completion(db: DbSession, iteration_id: UUID) -> None:
    """Check if all proposals are done and update iteration status."""
    proposal_repo = ProposalRepository(db)
    iter_repo = IterationRepository(db)

    proposals = proposal_repo.get_all_for_iteration(iteration_id)
    if not proposals:
        return

    all_done = all(p.status in (ProposalStatus.COMPLETED, ProposalStatus.FAILED) for p in proposals)
    if all_done:
        any_succeeded = any(p.status == ProposalStatus.COMPLETED for p in proposals)
        new_status = IterationStatus.COMPLETED if any_succeeded else IterationStatus.FAILED
        result = _update_iteration_status_with_retry(iter_repo, iteration_id, new_status)
        if result:
            logger.info("Iteration %s completed: %s", iteration_id, new_status)
