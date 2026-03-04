import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.infra.k8s_client import K8sClient
from app.infra.s3_client import S3Client
from app.workflow.state import SessionCreatePRState

logger = logging.getLogger(__name__)


async def create_k8s_job(state: SessionCreatePRState) -> dict:
    """Create the K8s Job for session-based PR creation."""
    k8s = K8sClient()
    job_name = k8s.create_session_pr_job(
        session_id=state["session_id"],
        iteration_index=state["iteration_index"],
        repo_url=state["repo_url"],
        branch=state["branch"],
        proposal_index=state["proposal_index"],
    )

    from app.di.container import DIContainer

    DIContainer.get_log_stream_client().register_job(
        session_id=state["session_id"],
        job_name=job_name,
        job_type="createpr",
        proposal_index=state["proposal_index"],
    )

    return {"k8s_job_name": job_name, "status": "running"}


async def wait_for_job(state: SessionCreatePRState) -> dict:
    """Poll K8s Job until completion."""
    k8s = K8sClient()
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


async def extract_results(state: SessionCreatePRState) -> dict:
    """Read PR URL from S3."""
    s3 = S3Client()
    pr_url_key = s3.pr_url_key(
        state["session_id"], state["iteration_index"], state["proposal_index"]
    )
    pr_url = s3.download_text(pr_url_key)
    if pr_url:
        return {"pr_url": pr_url.strip()}
    return {"error": "PR URL not found in S3", "status": "failed"}


def route_after_wait(state: SessionCreatePRState) -> str:
    if state["status"] == "succeeded":
        return "extract_results"
    return END


def build_session_create_pr_graph() -> Any:
    """Build and compile the session-based PR creation LangGraph."""
    graph = StateGraph(SessionCreatePRState)

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
