import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.di.dependencies import get_artifact_service, get_db
from app.model.job import Job, Proposal
from app.repository.job_repository import JobRepository
from app.schema.job_schema import (
    CreateJobRequest,
    ImplementRequest,
    JobResponse,
    ProposalResponse,
)
from app.service.artifact_service import ArtifactService
from app.usecase.job_usecase import CreateJobUseCase, ImplementProposalUseCase

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_proposal_response(proposal: Proposal, job_id: UUID) -> ProposalResponse:
    """Convert Proposal model to ProposalResponse."""
    try:
        plan = json.loads(proposal.plan) if proposal.plan else []
    except json.JSONDecodeError:
        plan = []
    try:
        files = json.loads(proposal.files) if proposal.files else []
    except json.JSONDecodeError:
        files = []

    return ProposalResponse(
        id=proposal.id,
        proposal_index=proposal.proposal_index,
        title=proposal.title,
        concept=proposal.concept,
        plan=plan,
        files=files,
        complexity=proposal.complexity,
        status=proposal.status.value if proposal.status else "pending",
        after_screenshot_url=(
            f"/api/jobs/{job_id}/proposals/{proposal.proposal_index}/screenshot"
            if proposal.after_screenshot_path
            else None
        ),
        error_message=proposal.error_message,
        created_at=proposal.created_at,
    )


def _to_job_response(job: Job) -> JobResponse:
    """Convert Job model to JobResponse."""
    job_id = job.id
    proposals = [_to_proposal_response(p, job_id) for p in job.proposals]  # type: ignore[arg-type]
    return JobResponse(
        id=job_id,
        status=job.status.value if job.status else "pending",
        repo_url=job.repo_url,
        branch=job.branch,
        instruction=job.instruction,
        before_screenshot_url=(
            f"/api/jobs/{job.id}/screenshot/before" if job.before_screenshot_path else None
        ),
        error_message=job.error_message,
        proposals=proposals,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(request: CreateJobRequest, db: Session = Depends(get_db)) -> JobResponse:
    usecase = CreateJobUseCase(db)
    job = await usecase.execute(
        repo_url=request.repo_url,
        branch=request.branch,
        instruction=request.instruction,
    )
    return _to_job_response(job)


@router.get("/", response_model=list[JobResponse])
async def list_jobs(db: Session = Depends(get_db)) -> list[JobResponse]:
    job_repo = JobRepository(db)
    jobs = job_repo.list_all()
    return [_to_job_response(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, db: Session = Depends(get_db)) -> JobResponse:
    job_repo = JobRepository(db)
    job = job_repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job_response(job)


@router.post("/{job_id}/implement", response_model=JobResponse)
async def implement_proposals(
    job_id: UUID, request: ImplementRequest, db: Session = Depends(get_db)
) -> JobResponse:
    usecase = ImplementProposalUseCase(db)
    try:
        job = await usecase.execute(job_id, request.proposal_indices)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_job_response(job)


@router.get("/{job_id}/screenshot/before")
async def get_before_screenshot(
    job_id: UUID, artifacts: ArtifactService = Depends(get_artifact_service)
) -> FileResponse:
    path = artifacts.get_before_screenshot_path(str(job_id))
    if not path:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(path), media_type="image/png")


@router.get("/{job_id}/proposals/{proposal_index}/screenshot")
async def get_after_screenshot(
    job_id: UUID,
    proposal_index: int,
    artifacts: ArtifactService = Depends(get_artifact_service),
) -> FileResponse:
    path = artifacts.get_after_screenshot_path(str(job_id), proposal_index)
    if not path:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(path), media_type="image/png")


@router.get("/{job_id}/proposals/{proposal_index}/diff")
async def get_diff(
    job_id: UUID,
    proposal_index: int,
    artifacts: ArtifactService = Depends(get_artifact_service),
) -> dict:
    diff = artifacts.get_diff(str(job_id), proposal_index)
    if not diff:
        raise HTTPException(status_code=404, detail="Diff not found")
    return {"diff": diff}
