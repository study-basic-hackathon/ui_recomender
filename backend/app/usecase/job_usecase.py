import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.model.job import Job, JobStatus, Proposal, ProposalStatus
from app.repository.database import SessionLocal
from app.repository.job_repository import JobRepository
from app.repository.proposal_repository import ProposalRepository
from app.service.artifact_service import ArtifactService
from app.workflow.analyzer_graph import build_analyzer_graph
from app.workflow.create_pr_graph import build_create_pr_graph
from app.workflow.implementation_graph import build_implementation_graph

logger = logging.getLogger(__name__)


class CreateJobUseCase:
    """Create a new job and trigger the analysis workflow."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.job_repo = JobRepository(db)

    async def execute(self, repo_url: str, branch: str, instruction: str) -> Job:
        job = Job(
            repo_url=repo_url,
            branch=branch,
            instruction=instruction,
            status=JobStatus.PENDING,
        )
        job = self.job_repo.create(job)
        job_id = str(job.id)

        # Run analysis in background (separate DB session)
        asyncio.create_task(
            CreateJobUseCase._run_analysis(job_id, repo_url, branch, instruction)
        )

        return job

    @staticmethod
    async def _run_analysis(
        job_id: str,
        repo_url: str,
        branch: str,
        instruction: str,
        parent_job_id: str | None = None,
        parent_proposal_index: int | None = None,
    ) -> None:
        """Background task: run the analyzer LangGraph workflow."""
        db = SessionLocal()
        try:
            job_repo = JobRepository(db)
            proposal_repo = ProposalRepository(db)

            job_repo.update_status(UUID(job_id), JobStatus.ANALYZING)

            graph = build_analyzer_graph()
            result = await graph.ainvoke(
                {
                    "job_id": job_id,
                    "repo_url": repo_url,
                    "branch": branch,
                    "instruction": instruction,
                    "num_proposals": get_settings().MAX_PROPOSALS,
                    "k8s_job_name": None,
                    "status": "pending",
                    "error": None,
                    "proposals": None,
                    "before_screenshot_path": None,
                    "parent_job_id": parent_job_id,
                    "parent_proposal_index": parent_proposal_index,
                }
            )

            if result.get("proposals"):
                proposals = []
                for i, prop in enumerate(result["proposals"]):
                    proposal = Proposal(
                        job_id=UUID(job_id),  # type: ignore[arg-type]
                        proposal_index=i,
                        title=prop.get("title", f"Proposal {i + 1}"),
                        concept=prop.get("concept", ""),
                        plan=json.dumps(prop.get("plan", []), ensure_ascii=False),
                        files=json.dumps(prop.get("files", []), ensure_ascii=False),
                        complexity=prop.get("complexity", "medium"),
                        status=ProposalStatus.PENDING,
                    )
                    proposals.append(proposal_repo.create(proposal))

                job_repo.update_status(
                    UUID(job_id),
                    JobStatus.ANALYZED,
                    before_screenshot_path=result.get("before_screenshot_path"),
                )
                logger.info(
                    "Analysis completed for job %s: %d proposals",
                    job_id,
                    len(result["proposals"]),
                )

                # Auto-trigger implementation for ALL proposals
                job_repo.update_status(UUID(job_id), JobStatus.IMPLEMENTING)
                repo_url = result.get("repo_url", repo_url)
                for proposal in proposals:
                    asyncio.create_task(
                        ImplementProposalUseCase._run_implementation_static(
                            str(job_id),
                            repo_url,
                            branch,
                            proposal.proposal_index or 0,
                            str(proposal.id),
                            str(proposal.plan),
                            parent_job_id=parent_job_id,
                            parent_proposal_index=parent_proposal_index,
                        )
                    )
                logger.info(
                    "Auto-triggered implementation for all %d proposals of job %s",
                    len(proposals),
                    job_id,
                )
            else:
                error = result.get("error", "No proposals generated")
                job_repo.update_status(UUID(job_id), JobStatus.FAILED, error_message=error)
                logger.warning("Analysis failed for job %s: %s", job_id, error)

        except Exception:
            logger.exception("Analysis failed for job %s", job_id)
            try:
                job_repo.update_status(
                    UUID(job_id),
                    JobStatus.FAILED,
                    error_message="Internal error during analysis",
                )
            except Exception:
                logger.exception("Failed to update job status for %s", job_id)
        finally:
            db.close()


class ImplementProposalUseCase:
    """Trigger implementation of selected proposals."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.job_repo = JobRepository(db)
        self.proposal_repo = ProposalRepository(db)

    async def execute(self, job_id: UUID, proposal_indices: list[int]) -> Job:
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError("Job not found")
        if job.status != JobStatus.ANALYZED:
            raise ValueError(f"Job is not in analyzed state: {job.status}")

        self.job_repo.update_status(job_id, JobStatus.IMPLEMENTING)

        parent_jid = str(job.parent_job_id) if job.parent_job_id else None
        parent_pidx = job.parent_proposal_index

        for idx in proposal_indices:
            proposal = self.proposal_repo.get_by_job_and_index(job_id, idx)
            if proposal:
                asyncio.create_task(
                    self._run_implementation_static(
                        str(job_id),
                        str(job.repo_url),
                        str(job.branch),
                        idx,
                        str(proposal.id),
                        str(proposal.plan),
                        parent_job_id=parent_jid,
                        parent_proposal_index=parent_pidx,
                    )
                )

        # Return the updated job
        updated_job = self.job_repo.get_by_id(job_id)
        if not updated_job:
            raise ValueError("Job not found after update")
        return updated_job

    @staticmethod
    async def _run_implementation_static(
        job_id: str,
        repo_url: str,
        branch: str,
        proposal_index: int,
        proposal_id: str,
        plan_json: str,
        parent_job_id: str | None = None,
        parent_proposal_index: int | None = None,
    ) -> None:
        """Background task: run one implementation LangGraph workflow."""
        db = SessionLocal()
        try:
            proposal_repo = ProposalRepository(db)

            proposal_repo.update_status(UUID(proposal_id), ProposalStatus.IMPLEMENTING)

            # Write plan to artifact dir for the worker to read
            artifacts = ArtifactService()
            artifacts.write_proposal_plan(job_id, proposal_index, plan_json)

            graph = build_implementation_graph()
            result = await graph.ainvoke(
                {
                    "job_id": job_id,
                    "repo_url": repo_url,
                    "branch": branch,
                    "proposal_index": proposal_index,
                    "proposal_plan": plan_json,
                    "k8s_job_name": None,
                    "status": "pending",
                    "error": None,
                    "after_screenshot_path": None,
                    "diff_content": None,
                    "parent_job_id": parent_job_id,
                    "parent_proposal_index": parent_proposal_index,
                }
            )

            if result.get("status") == "succeeded" or result.get("after_screenshot_path"):
                proposal_repo.update_status(
                    UUID(proposal_id),
                    ProposalStatus.COMPLETED,
                    after_screenshot_path=result.get("after_screenshot_path"),
                    diff_path=result.get("diff_content"),
                )
                logger.info(
                    "Implementation completed for proposal %d of job %s",
                    proposal_index,
                    job_id,
                )
            else:
                error = result.get("error", "Implementation failed")
                proposal_repo.update_status(
                    UUID(proposal_id),
                    ProposalStatus.FAILED,
                    error_message=error,
                )
                logger.warning(
                    "Implementation failed for proposal %d of job %s: %s",
                    proposal_index,
                    job_id,
                    error,
                )

            # Check if all proposals are done and update job status
            ImplementProposalUseCase._check_job_completion(db, UUID(job_id))

        except Exception:
            logger.exception(
                "Implementation failed for proposal %d of job %s",
                proposal_index,
                job_id,
            )
            try:
                proposal_repo.update_status(
                    UUID(proposal_id),
                    ProposalStatus.FAILED,
                    error_message="Internal error during implementation",
                )
                ImplementProposalUseCase._check_job_completion(db, UUID(job_id))
            except Exception:
                logger.exception("Failed to update proposal status")
        finally:
            db.close()

    @staticmethod
    def _check_job_completion(db: Session, job_id: UUID) -> None:
        """Check if all proposals are in terminal state and update job accordingly."""
        proposal_repo = ProposalRepository(db)
        job_repo = JobRepository(db)

        proposals = proposal_repo.get_all_for_job(job_id)
        if not proposals:
            return

        all_done = all(
            p.status in (ProposalStatus.COMPLETED, ProposalStatus.FAILED) for p in proposals
        )
        if all_done:
            any_succeeded = any(p.status == ProposalStatus.COMPLETED for p in proposals)
            new_status = JobStatus.COMPLETED if any_succeeded else JobStatus.FAILED
            job_repo.update_status(job_id, new_status)
            logger.info("Job %s completed with status: %s", job_id, new_status)


class ContinueJobUseCase:
    """Create a continuation job from a completed proposal."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.job_repo = JobRepository(db)
        self.proposal_repo = ProposalRepository(db)

    async def execute(
        self, parent_job_id: UUID, parent_proposal_index: int, instruction: str
    ) -> Job:
        parent_job = self.job_repo.get_by_id(parent_job_id)
        if not parent_job:
            raise ValueError("Parent job not found")
        if parent_job.status != JobStatus.COMPLETED:
            raise ValueError(f"Parent job is not completed: {parent_job.status}")

        parent_proposal = self.proposal_repo.get_by_job_and_index(
            parent_job_id, parent_proposal_index
        )
        if not parent_proposal:
            raise ValueError(f"Proposal {parent_proposal_index} not found")
        if parent_proposal.status != ProposalStatus.COMPLETED:
            raise ValueError(f"Proposal is not completed: {parent_proposal.status}")

        artifacts = ArtifactService()
        diff = artifacts.get_diff(str(parent_job_id), parent_proposal_index)
        if not diff:
            raise ValueError("No patch file found for the parent proposal")

        child_job = Job(
            repo_url=parent_job.repo_url,
            branch=parent_job.branch,
            instruction=instruction,
            status=JobStatus.PENDING,
            parent_job_id=parent_job_id,
            parent_proposal_index=parent_proposal_index,
        )
        child_job = self.job_repo.create(child_job)
        child_job_id = str(child_job.id)

        asyncio.create_task(
            CreateJobUseCase._run_analysis(
                child_job_id,
                str(parent_job.repo_url),
                str(parent_job.branch),
                instruction,
                parent_job_id=str(parent_job_id),
                parent_proposal_index=parent_proposal_index,
            )
        )

        return child_job


class CreatePRUseCase:
    """Trigger PR creation for a completed proposal."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.job_repo = JobRepository(db)
        self.proposal_repo = ProposalRepository(db)

    async def execute(self, job_id: UUID, proposal_index: int) -> Proposal:
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError("Job not found")

        proposal = self.proposal_repo.get_by_job_and_index(job_id, proposal_index)
        if not proposal:
            raise ValueError(f"Proposal {proposal_index} not found")
        if proposal.status != ProposalStatus.COMPLETED:
            raise ValueError(f"Proposal is not completed: {proposal.status}")
        if proposal.pr_status == "created":
            raise ValueError("PR already created")
        if proposal.pr_status == "creating":
            raise ValueError("PR creation already in progress")

        proposal_id = UUID(str(proposal.id))
        self.proposal_repo.update_status(proposal_id, proposal.status, pr_status="creating")

        asyncio.create_task(
            self._run_create_pr(
                str(job_id),
                str(job.repo_url),
                str(job.branch),
                proposal_index,
                str(proposal.id),
            )
        )

        updated = self.proposal_repo.get_by_id(proposal_id)
        if not updated:
            raise ValueError("Proposal not found after update")
        return updated

    @staticmethod
    async def _run_create_pr(
        job_id: str,
        repo_url: str,
        branch: str,
        proposal_index: int,
        proposal_id: str,
    ) -> None:
        """Background task: run the PR creation LangGraph workflow."""
        db = SessionLocal()
        try:
            proposal_repo = ProposalRepository(db)

            graph = build_create_pr_graph()
            result = await graph.ainvoke(
                {
                    "job_id": job_id,
                    "repo_url": repo_url,
                    "branch": branch,
                    "proposal_index": proposal_index,
                    "k8s_job_name": None,
                    "status": "pending",
                    "error": None,
                    "pr_url": None,
                }
            )

            if result.get("pr_url"):
                proposal_repo.update_status(
                    UUID(proposal_id),
                    ProposalStatus.COMPLETED,
                    pr_url=result["pr_url"],
                    pr_status="created",
                )
                logger.info(
                    "PR created for proposal %d of job %s: %s",
                    proposal_index,
                    job_id,
                    result["pr_url"],
                )
            else:
                error = result.get("error", "PR creation failed")
                proposal_repo.update_status(
                    UUID(proposal_id),
                    ProposalStatus.COMPLETED,
                    pr_status="failed",
                    error_message=error,
                )
                logger.warning(
                    "PR creation failed for proposal %d of job %s: %s",
                    proposal_index,
                    job_id,
                    error,
                )

        except Exception:
            logger.exception(
                "PR creation failed for proposal %d of job %s",
                proposal_index,
                job_id,
            )
            try:
                proposal_repo.update_status(
                    UUID(proposal_id),
                    ProposalStatus.COMPLETED,
                    pr_status="failed",
                    error_message="Internal error during PR creation",
                )
            except Exception:
                logger.exception("Failed to update proposal PR status")
        finally:
            db.close()
