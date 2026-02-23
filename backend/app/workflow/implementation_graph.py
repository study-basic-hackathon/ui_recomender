import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.service.artifact_service import ArtifactService
from app.service.k8s_service import K8sService
from app.workflow.state import ImplementationState

logger = logging.getLogger(__name__)


async def create_k8s_job(state: ImplementationState) -> dict:
    """Create the K8s Job for implementation."""
    k8s = K8sService()

    # Write proposal plan to artifact directory to avoid K8s env var size limits
    artifacts = ArtifactService()
    artifacts.write_proposal_plan(state["job_id"], state["proposal_index"], state["proposal_plan"])

    job_name = k8s.create_implementation_job(
        job_id=state["job_id"],
        repo_url=state["repo_url"],
        branch=state["branch"],
        proposal_index=state["proposal_index"],
        proposal_plan=state["proposal_plan"],
    )
    return {"k8s_job_name": job_name, "status": "running"}


async def wait_for_job(state: ImplementationState) -> dict:
    """Poll K8s Job until completion."""
    k8s = K8sService()
    k8s_job_name = state["k8s_job_name"]
    assert k8s_job_name is not None
    result = await k8s.wait_for_job(k8s_job_name)

    if result == "succeeded":
        return {"status": "succeeded"}

    logs = k8s.get_job_logs(k8s_job_name)
    error_msg = f"Implementation job {result}."
    if logs:
        error_msg += f" Logs: {logs[:500]}"
    return {"status": "failed", "error": error_msg}


async def extract_results(state: ImplementationState) -> dict:
    """Extract artifacts from pod logs and read results."""
    k8s = K8sService()
    artifacts = ArtifactService()

    # Get pod logs and extract embedded artifacts
    k8s_job_name = state["k8s_job_name"]
    assert k8s_job_name is not None
    logs = k8s.get_job_logs(k8s_job_name)
    if logs:
        artifacts.extract_impl_artifacts_from_logs(state["job_id"], state["proposal_index"], logs)

    after_path = artifacts.get_after_screenshot_path(state["job_id"], state["proposal_index"])
    diff_content = artifacts.get_diff(state["job_id"], state["proposal_index"])

    return {
        "after_screenshot_path": str(after_path) if after_path else None,
        "diff_content": diff_content,
    }


def route_after_wait(state: ImplementationState) -> str:
    """Route based on job completion status."""
    if state["status"] == "succeeded":
        return "extract_results"
    return END


def build_implementation_graph() -> Any:
    """Build and compile the implementation LangGraph."""
    graph = StateGraph(ImplementationState)

    graph.add_node("create_k8s_job", create_k8s_job)
    graph.add_node("wait_for_job", wait_for_job)
    graph.add_node("extract_results", extract_results)

    graph.add_edge(START, "create_k8s_job")
    graph.add_edge("create_k8s_job", "wait_for_job")
    graph.add_conditional_edges(
        "wait_for_job",
        route_after_wait,
        {"extract_results": "extract_results", END: END},
    )
    graph.add_edge("extract_results", END)

    return graph.compile()
