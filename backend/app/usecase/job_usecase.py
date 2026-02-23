import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.model.job import Job, JobStatus, Proposal, ProposalStatus
from app.repository.database import SessionLocal
from app.repository.job_repository import JobRepository
from app.repository.proposal_repository import ProposalRepository
from app.service.artifact_service import ArtifactService
from app.workflow.analyzer_graph import build_analyzer_graph
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
        asyncio.create_task(self._run_analysis(job_id, repo_url, branch, instruction))

        return job

    async def _run_analysis(
        self, job_id: str, repo_url: str, branch: str, instruction: str
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
                    "num_proposals": settings.MAX_PROPOSALS,
                    "k8s_job_name": None,
                    "status": "pending",
                    "error": None,
                    "proposals": None,
                    "before_screenshot_path": None,
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

        for idx in proposal_indices:
            proposal = self.proposal_repo.get_by_job_and_index(job_id, idx)
            if proposal:
                asyncio.create_task(
                    self._run_implementation(
                        str(job_id),
                        str(job.repo_url),
                        str(job.branch),
                        idx,
                        str(proposal.id),
                        str(proposal.plan),
                    )
                )

        # Return the updated job
        updated_job = self.job_repo.get_by_id(job_id)
        if not updated_job:
            raise ValueError("Job not found after update")
        return updated_job

    async def _run_implementation(
        self,
        job_id: str,
        repo_url: str,
        branch: str,
        proposal_index: int,
        proposal_id: str,
        plan_json: str,
    ) -> None:
        await self._run_implementation_static(
            job_id, repo_url, branch, proposal_index, proposal_id, plan_json
        )

    @staticmethod
    async def _run_implementation_static(
        job_id: str,
        repo_url: str,
        branch: str,
        proposal_index: int,
        proposal_id: str,
        plan_json: str,
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
