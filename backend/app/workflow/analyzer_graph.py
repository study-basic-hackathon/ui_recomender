import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.service.artifact_service import ArtifactService
from app.service.k8s_service import K8sService
from app.workflow.state import AnalyzerState

logger = logging.getLogger(__name__)


async def create_k8s_job(state: AnalyzerState) -> dict:
    """Create the K8s Job for analysis."""
    k8s = K8sService()
    job_name = k8s.create_analyzer_job(
        job_id=state["job_id"],
        repo_url=state["repo_url"],
        branch=state["branch"],
        instruction=state["instruction"],
        num_proposals=state["num_proposals"],
    )
    return {"k8s_job_name": job_name, "status": "running"}


async def wait_for_job(state: AnalyzerState) -> dict:
    """Poll K8s Job until completion."""
    k8s = K8sService()
    k8s_job_name = state["k8s_job_name"]
    assert k8s_job_name is not None
    result = await k8s.wait_for_job(k8s_job_name)

    if result == "succeeded":
        return {"status": "succeeded"}

    logs = k8s.get_job_logs(k8s_job_name)
    error_msg = f"Analyzer job {result}."
    if logs:
        error_msg += f" Logs: {logs[:500]}"
    return {"status": "failed", "error": error_msg}


async def extract_results(state: AnalyzerState) -> dict:
    """Extract artifacts from pod logs and read results."""
    k8s = K8sService()
    artifacts = ArtifactService()

    # Get pod logs and extract embedded artifacts
    k8s_job_name = state["k8s_job_name"]
    assert k8s_job_name is not None
    logs = k8s.get_job_logs(k8s_job_name)
    if logs:
        artifacts.extract_artifacts_from_logs(state["job_id"], logs)

    proposals = artifacts.get_proposals_json(state["job_id"])
    before_path = artifacts.get_before_screenshot_path(state["job_id"])

    if proposals:
        return {
            "proposals": proposals,
            "before_screenshot_path": str(before_path) if before_path else None,
        }
    return {"error": "Failed to parse proposals from worker output", "status": "failed"}


def route_after_wait(state: AnalyzerState) -> str:
    """Route based on job completion status."""
    if state["status"] == "succeeded":
        return "extract_results"
    return END


def build_analyzer_graph() -> Any:
    """Build and compile the analyzer LangGraph."""
    graph = StateGraph(AnalyzerState)

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
