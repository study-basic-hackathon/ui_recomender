from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    repo_url: str = Field(..., max_length=500, description="GitHub repository URL")
    branch: str = Field(default="main", max_length=200, description="Base branch name")
    instruction: str = Field(..., min_length=1, description="UI change instruction")


class IterateRequest(BaseModel):
    selected_proposal_index: int = Field(
        ..., ge=0, description="Index of the proposal selected from the previous iteration"
    )
    instruction: str = Field(..., min_length=1, description="Additional UI refinement instruction")


class CreatePRRequest(BaseModel):
    iteration_index: int = Field(..., ge=0, description="Iteration index")
    proposal_index: int = Field(..., ge=0, description="Proposal index within the iteration")


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    proposal_index: int
    title: str
    concept: str
    plan: list[str]
    files: list[dict]
    complexity: str | None
    status: str
    after_screenshot_url: str | None = None
    diff_key: str | None = None
    pr_url: str | None = None
    pr_status: str | None = None
    error_message: str | None = None
    created_at: datetime


class IterationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    iteration_index: int
    instruction: str
    selected_proposal_index: int | None = None
    status: str
    before_screenshot_url: str | None = None
    error_message: str | None = None
    proposals: list[ProposalResponse] = []
    created_at: datetime


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repo_url: str
    base_branch: str
    status: str
    iterations: list[IterationResponse] = []
    created_at: datetime
    updated_at: datetime
