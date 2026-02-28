from typing import TypedDict


class SessionAnalyzerState(TypedDict):
    """State for the session-based analyzer workflow."""

    # Input
    session_id: str
    iteration_index: int
    repo_url: str
    branch: str
    instruction: str
    num_proposals: int

    # Patch context (for iter > 0)
    selected_proposal_index: int | None  # from previous iteration

    # Intermediate
    k8s_job_name: str | None
    status: str  # pending, running, succeeded, failed, timeout
    error: str | None

    # Output
    proposals: list[dict] | None
    before_screenshot_key: str | None


class SessionImplementationState(TypedDict):
    """State for the session-based implementation workflow."""

    # Input
    session_id: str
    iteration_index: int
    repo_url: str
    branch: str
    proposal_index: int
    proposal_plan: str

    # Patch context (for iter > 0)
    selected_proposal_index: int | None

    # Intermediate
    k8s_job_name: str | None
    status: str
    error: str | None

    # Output
    after_screenshot_key: str | None
    diff_key: str | None


class SessionCreatePRState(TypedDict):
    """State for the session-based PR creation workflow."""

    # Input
    session_id: str
    iteration_index: int
    repo_url: str
    branch: str
    proposal_index: int

    # Intermediate
    k8s_job_name: str | None
    status: str
    error: str | None

    # Output
    pr_url: str | None
