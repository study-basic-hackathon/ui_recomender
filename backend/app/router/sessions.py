import json
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.di.dependencies import get_db, get_s3_service
from app.model.session import Iteration, Proposal
from app.model.session import Session as SessionModel
from app.schema.session_schema import (
    CreatePRRequest,
    CreateSessionRequest,
    IterateRequest,
    IterationResponse,
    ProposalResponse,
    SessionResponse,
)
from app.service.s3_service import S3Service
from app.usecase.session_usecase import (
    CreateSessionPRUseCase,
    CreateSessionUseCase,
    IterateUseCase,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _to_proposal_response(
    proposal: Proposal, session_id: UUID, iteration_index: int
) -> ProposalResponse:
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
            f"/api/sessions/{session_id}/iterations/{iteration_index}"
            f"/proposals/{proposal.proposal_index}/screenshot"
            if proposal.after_screenshot_key
            else None
        ),
        diff_key=proposal.diff_key,
        pr_url=proposal.pr_url,
        pr_status=proposal.pr_status,
        error_message=proposal.error_message,
        created_at=proposal.created_at,
    )


def _to_iteration_response(iteration: Iteration, session_id: UUID) -> IterationResponse:
    proposals = [
        _to_proposal_response(p, session_id, iteration.iteration_index) for p in iteration.proposals
    ]
    return IterationResponse(
        id=iteration.id,
        iteration_index=iteration.iteration_index,
        instruction=iteration.instruction,
        selected_proposal_index=iteration.selected_proposal_index,
        status=iteration.status.value if iteration.status else "pending",
        before_screenshot_url=(
            f"/api/sessions/{session_id}/iterations/{iteration.iteration_index}/screenshot/before"
            if iteration.before_screenshot_key
            else None
        ),
        error_message=iteration.error_message,
        proposals=proposals,
        created_at=iteration.created_at,
    )


def _to_session_response(
    session: "SessionModel",
) -> SessionResponse:
    session_id = session.id
    iterations = [_to_iteration_response(it, session_id) for it in session.iterations]
    return SessionResponse(
        id=session_id,
        repo_url=session.repo_url,
        base_branch=session.base_branch,
        status=session.status.value if session.status else "active",
        iterations=iterations,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post("/", response_model=SessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest, db: Session = Depends(get_db)
) -> SessionResponse:
    usecase = CreateSessionUseCase(db)
    session = await usecase.execute(
        repo_url=request.repo_url,
        branch=request.branch,
        instruction=request.instruction,
    )
    return _to_session_response(session)


@router.get("/", response_model=list[SessionResponse])
async def list_sessions(db: Session = Depends(get_db)) -> list[SessionResponse]:
    from app.repository.session_repository import SessionRepository

    repo = SessionRepository(db)
    sessions = repo.list_all()
    return [_to_session_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: UUID, db: Session = Depends(get_db)) -> SessionResponse:
    from app.repository.session_repository import SessionRepository

    repo = SessionRepository(db)
    session = repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_session_response(session)


@router.post("/{session_id}/iterate", response_model=SessionResponse, status_code=201)
async def iterate(
    session_id: UUID,
    request: IterateRequest,
    db: Session = Depends(get_db),
) -> SessionResponse:
    usecase = IterateUseCase(db)
    try:
        session = await usecase.execute(
            session_id, request.selected_proposal_index, request.instruction
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_session_response(session)


@router.post("/{session_id}/create-pr", response_model=ProposalResponse)
async def create_pr(
    session_id: UUID,
    request: CreatePRRequest,
    db: Session = Depends(get_db),
) -> ProposalResponse:
    usecase = CreateSessionPRUseCase(db)
    try:
        proposal = await usecase.execute(
            session_id, request.iteration_index, request.proposal_index
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_proposal_response(proposal, session_id, request.iteration_index)


@router.get("/{session_id}/iterations/{iter_index}/screenshot/before")
async def get_before_screenshot(
    session_id: UUID,
    iter_index: int,
    s3: S3Service = Depends(get_s3_service),
) -> StreamingResponse:
    data = s3.get_before_screenshot(str(session_id), iter_index)
    if not data:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return StreamingResponse(BytesIO(data), media_type="image/png")


@router.get("/{session_id}/iterations/{iter_index}/proposals/{prop_index}/screenshot")
async def get_after_screenshot(
    session_id: UUID,
    iter_index: int,
    prop_index: int,
    s3: S3Service = Depends(get_s3_service),
) -> StreamingResponse:
    data = s3.get_after_screenshot(str(session_id), iter_index, prop_index)
    if not data:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return StreamingResponse(BytesIO(data), media_type="image/png")


@router.get("/{session_id}/iterations/{iter_index}/proposals/{prop_index}/diff")
async def get_diff(
    session_id: UUID,
    iter_index: int,
    prop_index: int,
    s3: S3Service = Depends(get_s3_service),
) -> dict:
    diff = s3.get_diff(str(session_id), iter_index, prop_index)
    if not diff:
        raise HTTPException(status_code=404, detail="Diff not found")
    return {"diff": diff}
