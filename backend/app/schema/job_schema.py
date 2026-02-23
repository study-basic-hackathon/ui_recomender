from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateJobRequest(BaseModel):
    repo_url: str = Field(..., max_length=500, description="GitHub repository URL")
    branch: str = Field(default="main", max_length=200, description="Branch name")
    instruction: str = Field(..., min_length=1, description="UI change instruction")


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
    pr_url: str | None = None
    pr_status: str | None = None
    error_message: str | None = None
    created_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    repo_url: str
    branch: str
    instruction: str
    before_screenshot_url: str | None = None
    error_message: str | None = None
    proposals: list[ProposalResponse] = []
    created_at: datetime
    updated_at: datetime


class ImplementRequest(BaseModel):
    proposal_indices: list[int] = Field(..., description="Indices of proposals to implement")


class SettingRequest(BaseModel):
    key: str = Field(..., max_length=100)
    value: str


class SettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    updated_at: datetime
