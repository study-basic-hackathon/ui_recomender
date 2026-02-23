import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.service.artifact_service import ArtifactService
from app.service.k8s_service import K8sService
from app.workflow.state import CreatePRState

logger = logging.getLogger(__name__)


async def create_k8s_job(state: CreatePRState) -> dict:
    """Create the K8s Job for PR creation."""
    k8s = K8sService()
    job_name = k8s.create_pr_job(
        job_id=state["job_id"],
        repo_url=state["repo_url"],
        branch=state["branch"],
        proposal_index=state["proposal_index"],
    )
    return {"k8s_job_name": job_name, "status": "running"}


async def wait_for_job(state: CreatePRState) -> dict:
    """Poll K8s Job until completion."""
    k8s = K8sService()
    k8s_job_name = state["k8s_job_name"]
    assert k8s_job_name is not None
    result = await k8s.wait_for_job(k8s_job_name)

    if result == "succeeded":
        return {"status": "succeeded"}

    logs = k8s.get_job_logs(k8s_job_name)
    error_msg = f"PR creation job {result}."
    if logs:
        error_msg += f" Logs: {logs[:500]}"
    return {"status": "failed", "error": error_msg}


async def extract_results(state: CreatePRState) -> dict:
    """Extract PR URL artifact from pod logs."""
    k8s = K8sService()
    artifacts = ArtifactService()

    k8s_job_name = state["k8s_job_name"]
    assert k8s_job_name is not None
    logs = k8s.get_job_logs(k8s_job_name)
    if logs:
        artifacts.extract_impl_artifacts_from_logs(
            state["job_id"], state["proposal_index"], logs
        )

    pr_url = artifacts.get_pr_url(state["job_id"], state["proposal_index"])
    return {"pr_url": pr_url}


def route_after_wait(state: CreatePRState) -> str:
    """Route based on job completion status."""
    if state["status"] == "succeeded":
        return "extract_results"
    return END


def build_create_pr_graph() -> Any:
    """Build and compile the PR creation LangGraph."""
    graph = StateGraph(CreatePRState)

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
