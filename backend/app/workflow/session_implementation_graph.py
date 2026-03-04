import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.infra.k8s_client import K8sClient
from app.infra.s3_client import S3Client
from app.workflow.state import SessionImplementationState

logger = logging.getLogger(__name__)


async def create_k8s_job(state: SessionImplementationState) -> dict:
    """Create the K8s Job for session-based implementation."""
    k8s = K8sClient()
    s3 = S3Client()

    # Write proposal plan to S3 for the worker to read
    plan_key = s3.plan_key(state["session_id"], state["iteration_index"], state["proposal_index"])
    s3.upload_text(plan_key, state["proposal_plan"])

    job_name = k8s.create_session_implementation_job(
        session_id=state["session_id"],
        iteration_index=state["iteration_index"],
        repo_url=state["repo_url"],
        branch=state["branch"],
        proposal_index=state["proposal_index"],
        proposal_plan=state["proposal_plan"],
        selected_proposal_index=state.get("selected_proposal_index"),
    )

    from app.di.container import DIContainer

    DIContainer.get_log_stream_client().register_job(
        session_id=state["session_id"],
        job_name=job_name,
        job_type="implement",
        proposal_index=state["proposal_index"],
    )

    return {"k8s_job_name": job_name, "status": "running"}


async def wait_for_job(state: SessionImplementationState) -> dict:
    """Poll K8s Job until completion."""
    k8s = K8sClient()
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


async def extract_results(state: SessionImplementationState) -> dict:
    """Read implementation results from S3."""
    s3 = S3Client()
    session_id = state["session_id"]
    iteration_index = state["iteration_index"]
    proposal_index = state["proposal_index"]

    after_key = s3.after_screenshot_key(session_id, iteration_index, proposal_index)
    diff_k = s3.diff_key(session_id, iteration_index, proposal_index)

    has_after = s3.exists(after_key)
    has_diff = s3.exists(diff_k)

    return {
        "after_screenshot_key": after_key if has_after else None,
        "diff_key": diff_k if has_diff else None,
    }


def route_after_wait(state: SessionImplementationState) -> str:
    """Route based on job completion status."""
    if state["status"] == "succeeded":
        return "extract_results"
    return END


def build_session_implementation_graph() -> Any:
    """Build and compile the session-based implementation LangGraph."""
    graph = StateGraph(SessionImplementationState)

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
