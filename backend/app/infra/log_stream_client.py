import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.infra.k8s_client import K8sClient

logger = logging.getLogger(__name__)

LOG_PREFIX = "@@LOG@@"


@dataclass
class JobInfo:
    job_name: str
    job_type: str  # "analyze", "implement", "createpr"
    proposal_index: int | None = None


@dataclass
class SessionJobs:
    jobs: list[JobInfo] = field(default_factory=list)
    version: int = 0  # incremented when jobs list changes


def parse_log_line(line: str) -> dict | None:
    """Parse a log line. If it has the @@LOG@@ prefix, return the parsed JSON.
    Otherwise return a generic log entry."""
    if line.startswith(LOG_PREFIX):
        json_str = line[len(LOG_PREFIX) :]
        try:
            result: dict = json.loads(json_str)
            return result
        except json.JSONDecodeError:
            logger.debug("Failed to parse log JSON: %s", json_str[:100])
            return None
    return None


class LogStreamClient:
    """Manages log streaming for sessions. Singleton per backend process."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionJobs] = {}
        self._lock = asyncio.Lock()

    def register_job(
        self,
        session_id: str,
        job_name: str,
        job_type: str,
        proposal_index: int | None = None,
    ) -> None:
        """Register a K8s job for log streaming."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionJobs()
        session_jobs = self._sessions[session_id]
        # Avoid duplicate registration
        for existing in session_jobs.jobs:
            if existing.job_name == job_name:
                return
        session_jobs.jobs.append(
            JobInfo(job_name=job_name, job_type=job_type, proposal_index=proposal_index)
        )
        session_jobs.version += 1
        logger.info("Registered job %s (type=%s) for session %s", job_name, job_type, session_id)

    def get_session_jobs(self, session_id: str) -> list[JobInfo]:
        """Get registered jobs for a session."""
        session_jobs = self._sessions.get(session_id)
        if not session_jobs:
            return []
        return list(session_jobs.jobs)

    async def stream_session_logs(
        self, session_id: str, since_seconds: int | None = None
    ) -> AsyncIterator[dict]:
        """Stream logs from all jobs in a session, multiplexed into a single stream.
        Dynamically picks up new jobs as they are registered.

        Args:
            since_seconds: If set, only stream logs newer than this many seconds.
                           Used on reconnect to avoid replaying old logs.
        """
        k8s = K8sClient()
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        tracked_jobs: set[str] = set()
        tasks: list[asyncio.Task[None]] = []

        async def _stream_single_job(job_info: JobInfo) -> None:
            """Stream logs from a single job into the shared queue."""
            try:
                async for line in k8s.stream_pod_logs(
                    job_info.job_name, since_seconds=since_seconds
                ):
                    parsed = parse_log_line(line)
                    if parsed:
                        event = {
                            "job_type": job_info.job_type,
                            "proposal_index": job_info.proposal_index,
                            **parsed,
                        }
                        await queue.put(event)
                    else:
                        # Non-structured log lines (subprocess stdout, etc.) are internal — skip
                        pass
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("Error streaming job %s: %s", job_info.job_name, e)
                await queue.put(
                    {
                        "job_type": job_info.job_type,
                        "proposal_index": job_info.proposal_index,
                        "phase": "error",
                        "message": str(e),
                    }
                )

        async def _monitor_new_jobs() -> None:
            """Monitor for new job registrations and start streaming them."""
            try:
                while True:
                    session_jobs = self._sessions.get(session_id)
                    if session_jobs:
                        for job_info in session_jobs.jobs:
                            if job_info.job_name not in tracked_jobs:
                                tracked_jobs.add(job_info.job_name)
                                task = asyncio.create_task(_stream_single_job(job_info))
                                tasks.append(task)
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                return

        monitor_task = asyncio.create_task(_monitor_new_jobs())
        tasks.append(monitor_task)

        try:
            # Keep yielding events until all job streams complete
            no_event_count = 0
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    if event is not None:
                        no_event_count = 0
                        yield event
                except TimeoutError:
                    no_event_count += 1
                    # Check if all streaming tasks (excluding monitor) are done
                    streaming_tasks = [t for t in tasks if t is not monitor_task]
                    if streaming_tasks and all(t.done() for t in streaming_tasks):
                        # Drain remaining items
                        while not queue.empty():
                            event = queue.get_nowait()
                            if event is not None:
                                yield event
                        break
                    # After 5 minutes of no events and no active streams, stop
                    if no_event_count > 60:
                        break
                    # Send keepalive
                    yield {"job_type": "_keepalive", "phase": "waiting", "message": ""}
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def cleanup_session(self, session_id: str) -> None:
        """Remove session data after streaming is done."""
        self._sessions.pop(session_id, None)
