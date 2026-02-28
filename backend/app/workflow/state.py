from typing import TypedDict


class AnalyzerState(TypedDict):
    """State for the analyzer workflow."""

    # Input
    job_id: str
    repo_url: str
    branch: str
    instruction: str
    num_proposals: int

    # Optional chaining (continuation from parent proposal)
    parent_job_id: str | None
    parent_proposal_index: int | None

    # Intermediate
    k8s_job_name: str | None
    status: str  # pending, running, succeeded, failed, timeout
    error: str | None

    # Output
    proposals: list[dict] | None
    before_screenshot_path: str | None


class ImplementationState(TypedDict):
    """State for the implementation workflow."""

    # Input
    job_id: str
    repo_url: str
    branch: str
    proposal_index: int
    proposal_plan: str

    # Optional chaining (continuation from parent proposal)
    parent_job_id: str | None
    parent_proposal_index: int | None

    # Intermediate
    k8s_job_name: str | None
    status: str
    error: str | None

    # Output
    after_screenshot_path: str | None
    diff_content: str | None


class CreatePRState(TypedDict):
    """State for the PR creation workflow."""

    # Input
    job_id: str
    repo_url: str
    branch: str
    proposal_index: int

    # Intermediate
    k8s_job_name: str | None
    status: str
    error: str | None

    # Output
    pr_url: str | None
