class JobNotFoundError(Exception):
    """Raised when a job is not found."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Job not found: {job_id}")


class ProposalNotFoundError(Exception):
    """Raised when a proposal is not found."""

    def __init__(self, job_id: str, proposal_index: int) -> None:
        self.job_id = job_id
        self.proposal_index = proposal_index
        super().__init__(f"Proposal not found: job={job_id}, index={proposal_index}")


class K8sServiceError(Exception):
    """Raised when a Kubernetes operation fails."""


class ArtifactNotFoundError(Exception):
    """Raised when an artifact file is not found."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Artifact not found: {path}")


class InvalidJobStateError(Exception):
    """Raised when a job is in an invalid state for the requested operation."""

    def __init__(self, job_id: str, current_state: str, expected_state: str) -> None:
        self.job_id = job_id
        self.current_state = current_state
        self.expected_state = expected_state
        super().__init__(f"Job {job_id} is in state '{current_state}', expected '{expected_state}'")
