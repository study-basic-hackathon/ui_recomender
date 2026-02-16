from typing import Optional, TypedDict


class AnalyzerState(TypedDict):
    """State for the analyzer workflow."""

    # Input
    job_id: str
    repo_url: str
    branch: str
    instruction: str
    num_proposals: int

    # Intermediate
    k8s_job_name: Optional[str]
    status: str  # pending, running, succeeded, failed, timeout
    error: Optional[str]

    # Output
    proposals: Optional[list[dict]]
    before_screenshot_path: Optional[str]


class ImplementationState(TypedDict):
    """State for the implementation workflow."""

    # Input
    job_id: str
    repo_url: str
    branch: str
    proposal_index: int
    proposal_plan: str

    # Intermediate
    k8s_job_name: Optional[str]
    status: str
    error: Optional[str]

    # Output
    after_screenshot_path: Optional[str]
    diff_content: Optional[str]
