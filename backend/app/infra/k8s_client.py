import asyncio
import logging
from collections.abc import AsyncIterator

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class K8sClient:
    """Kubernetes Job management client."""

    def __init__(self) -> None:
        settings = get_settings()
        if settings.K8S_IN_CLUSTER:
            config.load_incluster_config()
        else:
            config.load_kube_config()
            # Docker コンテナ内からホストの K8s API にアクセスするため、
            # 127.0.0.1 を host.docker.internal に書き換える。
            # K8s 証明書は 127.0.0.1 向けなので SSL 検証もスキップする。
            k8s_config = client.Configuration.get_default_copy()
            if "127.0.0.1" in k8s_config.host:
                k8s_config.host = k8s_config.host.replace("127.0.0.1", "host.docker.internal")
                k8s_config.verify_ssl = False
                client.Configuration.set_default(k8s_config)
        self.batch_v1 = client.BatchV1Api()
        self.core_v1 = client.CoreV1Api()
        self.namespace = settings.K8S_NAMESPACE
        self.worker_image = settings.WORKER_IMAGE
        self.worker_deadline_seconds = settings.WORKER_DEADLINE_SECONDS

    def _build_worker_container(
        self, mode: str, env_vars: list[client.V1EnvVar]
    ) -> client.V1Container:
        """Build a worker container spec with common configuration."""
        base_env = [
            client.V1EnvVar(name="WORKER_MODE", value=mode),
            client.V1EnvVar(
                name="ANTHROPIC_API_KEY",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="ui-recommender-secrets",
                        key="anthropic-api-key",
                    )
                ),
            ),
            client.V1EnvVar(name="TERM", value="dumb"),
            client.V1EnvVar(name="CLAUDE_CODE_MAX_OUTPUT_TOKENS", value="128000"),
        ]
        return client.V1Container(
            name="worker",
            image=self.worker_image,
            image_pull_policy="Never",
            env=base_env + env_vars,
            resources=client.V1ResourceRequirements(
                requests={"memory": "1Gi", "cpu": "1000m"},
                limits={"memory": "4Gi", "cpu": "4000m"},
            ),
            volume_mounts=[
                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                client.V1VolumeMount(name="artifacts", mount_path="/artifacts"),
            ],
        )

    def _build_job_spec(
        self,
        job_name: str,
        labels: dict[str, str],
        container: client.V1Container,
    ) -> client.V1Job:
        """Build a K8s Job spec."""
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=client.V1PodSpec(
                restart_policy="Never",
                containers=[container],
                volumes=[
                    client.V1Volume(
                        name="workspace",
                        empty_dir=client.V1EmptyDirVolumeSource(),
                    ),
                    client.V1Volume(
                        name="artifacts",
                        host_path=client.V1HostPathVolumeSource(
                            path="/artifacts", type="DirectoryOrCreate"
                        ),
                    ),
                ],
            ),
        )
        return client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name, labels=labels),
            spec=client.V1JobSpec(
                template=template,
                backoff_limit=1,
                ttl_seconds_after_finished=1800,
                active_deadline_seconds=self.worker_deadline_seconds,
            ),
        )

    def _append_parent_env_vars(
        self,
        env_vars: list[client.V1EnvVar],
        parent_job_id: str | None,
        parent_proposal_index: int | None,
    ) -> None:
        """Append PARENT_JOB_ID / PARENT_PROPOSAL_INDEX env vars if set."""
        if parent_job_id is not None and parent_proposal_index is not None:
            env_vars.append(client.V1EnvVar(name="PARENT_JOB_ID", value=parent_job_id))
            env_vars.append(
                client.V1EnvVar(name="PARENT_PROPOSAL_INDEX", value=str(parent_proposal_index))
            )

    def create_analyzer_job(
        self,
        job_id: str,
        repo_url: str,
        branch: str,
        instruction: str,
        num_proposals: int,
        parent_job_id: str | None = None,
        parent_proposal_index: int | None = None,
    ) -> str:
        """Create a K8s Job for analysis. Returns the K8s job name."""
        job_name = f"ui-worker-{job_id[:8]}-analyze"
        labels = {
            "app": "ui-recommender",
            "component": "worker",
            "job-id": job_id[:8],
            "mode": "analyze",
        }
        env_vars = [
            client.V1EnvVar(name="JOB_ID", value=job_id),
            client.V1EnvVar(name="REPO_URL", value=repo_url),
            client.V1EnvVar(name="BRANCH", value=branch),
            client.V1EnvVar(name="INSTRUCTION", value=instruction),
            client.V1EnvVar(name="NUM_PROPOSALS", value=str(num_proposals)),
        ]
        self._append_parent_env_vars(env_vars, parent_job_id, parent_proposal_index)
        container = self._build_worker_container("analyze", env_vars)
        job = self._build_job_spec(job_name, labels, container)

        self.batch_v1.create_namespaced_job(namespace=self.namespace, body=job)
        logger.info("Created analyzer K8s Job: %s", job_name)
        return job_name

    def create_implementation_job(
        self,
        job_id: str,
        repo_url: str,
        branch: str,
        proposal_index: int,
        proposal_plan: str,
        parent_job_id: str | None = None,
        parent_proposal_index: int | None = None,
    ) -> str:
        """Create a K8s Job for implementation. Returns the K8s job name."""
        job_name = f"ui-worker-{job_id[:8]}-impl-{proposal_index}"
        labels = {
            "app": "ui-recommender",
            "component": "worker",
            "job-id": job_id[:8],
            "mode": "implement",
        }
        env_vars = [
            client.V1EnvVar(name="JOB_ID", value=job_id),
            client.V1EnvVar(name="REPO_URL", value=repo_url),
            client.V1EnvVar(name="BRANCH", value=branch),
            client.V1EnvVar(name="PROPOSAL_INDEX", value=str(proposal_index)),
            client.V1EnvVar(name="PROPOSAL_PLAN", value=proposal_plan),
        ]
        self._append_parent_env_vars(env_vars, parent_job_id, parent_proposal_index)
        container = self._build_worker_container("implement", env_vars)
        job = self._build_job_spec(job_name, labels, container)

        self.batch_v1.create_namespaced_job(namespace=self.namespace, body=job)
        logger.info("Created implementation K8s Job: %s", job_name)
        return job_name

    def create_pr_job(
        self,
        job_id: str,
        repo_url: str,
        branch: str,
        proposal_index: int,
    ) -> str:
        """Create a K8s Job for PR creation. Returns the K8s job name."""
        job_name = f"ui-worker-{job_id[:8]}-pr-{proposal_index}"
        labels = {
            "app": "ui-recommender",
            "component": "worker",
            "job-id": job_id[:8],
            "mode": "createpr",
        }
        env_vars = [
            client.V1EnvVar(name="JOB_ID", value=job_id),
            client.V1EnvVar(name="REPO_URL", value=repo_url),
            client.V1EnvVar(name="BRANCH", value=branch),
            client.V1EnvVar(name="PROPOSAL_INDEX", value=str(proposal_index)),
            client.V1EnvVar(
                name="GITHUB_TOKEN",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="ui-recommender-secrets",
                        key="github-token",
                    )
                ),
            ),
        ]
        container = self._build_worker_container("createpr", env_vars)
        job = self._build_job_spec(job_name, labels, container)

        self.batch_v1.create_namespaced_job(namespace=self.namespace, body=job)
        logger.info("Created PR creation K8s Job: %s", job_name)
        return job_name

    async def wait_for_job(self, job_name: str, timeout: int = 900, poll_interval: int = 5) -> str:
        """Poll K8s Job status until completion. Returns 'succeeded', 'failed', or 'timeout'."""
        elapsed = 0
        while elapsed < timeout:
            try:
                job = self.batch_v1.read_namespaced_job_status(
                    name=job_name, namespace=self.namespace
                )
                if job.status.succeeded and job.status.succeeded > 0:
                    logger.info("K8s Job %s succeeded", job_name)
                    return "succeeded"
                if job.status.failed and job.status.failed > 0:
                    logger.warning("K8s Job %s failed", job_name)
                    return "failed"
            except ApiException as e:
                logger.error("Error checking K8s Job %s: %s", job_name, e)
                return "failed"
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning("K8s Job %s timed out after %ds", job_name, timeout)
        return "timeout"

    def get_job_logs(self, job_name: str) -> str | None:
        """Get logs from the job's pod."""
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"job-name={job_name}",
            )
            if pods.items:
                return str(
                    self.core_v1.read_namespaced_pod_log(
                        name=pods.items[0].metadata.name,
                        namespace=self.namespace,
                    )
                )
        except ApiException as e:
            logger.error("Error getting logs for K8s Job %s: %s", job_name, e)
        return None

    # ── Session-based methods (S3 artifacts, no hostPath) ──

    def _build_s3_env_vars(self) -> list[client.V1EnvVar]:
        """Build S3-related env vars for session-based workers."""
        settings = get_settings()
        env = [
            client.V1EnvVar(name="S3_BUCKET", value=settings.S3_BUCKET),
            client.V1EnvVar(name="S3_REGION", value=settings.S3_REGION),
        ]
        endpoint = settings.S3_ENDPOINT_URL_K8S or settings.S3_ENDPOINT_URL
        if endpoint:
            env.append(client.V1EnvVar(name="S3_ENDPOINT_URL", value=endpoint))
            env.append(client.V1EnvVar(name="S3_ACCESS_KEY", value=settings.S3_ACCESS_KEY))
            env.append(client.V1EnvVar(name="S3_SECRET_KEY", value=settings.S3_SECRET_KEY))
        return env

    def _build_session_worker_container(
        self, mode: str, env_vars: list[client.V1EnvVar]
    ) -> client.V1Container:
        """Build a session-based worker container (no hostPath artifacts volume)."""
        base_env = [
            client.V1EnvVar(name="WORKER_MODE", value=mode),
            client.V1EnvVar(
                name="ANTHROPIC_API_KEY",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="ui-recommender-secrets",
                        key="anthropic-api-key",
                    )
                ),
            ),
            client.V1EnvVar(name="TERM", value="dumb"),
            client.V1EnvVar(name="CLAUDE_CODE_MAX_OUTPUT_TOKENS", value="128000"),
        ] + self._build_s3_env_vars()
        return client.V1Container(
            name="worker",
            image=self.worker_image,
            image_pull_policy="Never",
            env=base_env + env_vars,
            resources=client.V1ResourceRequirements(
                requests={"memory": "1Gi", "cpu": "1000m"},
                limits={"memory": "4Gi", "cpu": "4000m"},
            ),
            volume_mounts=[
                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
            ],
        )

    def _build_session_job_spec(
        self,
        job_name: str,
        labels: dict[str, str],
        container: client.V1Container,
    ) -> client.V1Job:
        """Build a K8s Job spec without hostPath artifacts volume."""
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=client.V1PodSpec(
                restart_policy="Never",
                containers=[container],
                volumes=[
                    client.V1Volume(
                        name="workspace",
                        empty_dir=client.V1EmptyDirVolumeSource(),
                    ),
                ],
            ),
        )
        return client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name, labels=labels),
            spec=client.V1JobSpec(
                template=template,
                backoff_limit=1,
                ttl_seconds_after_finished=1800,
                active_deadline_seconds=self.worker_deadline_seconds,
            ),
        )

    def _create_job_idempotent(self, job_name: str, job: client.V1Job) -> None:
        """Create a K8s Job, handling 409 AlreadyExists gracefully."""
        try:
            self.batch_v1.create_namespaced_job(namespace=self.namespace, body=job)
            logger.info("Created K8s Job: %s", job_name)
        except ApiException as e:
            if e.status == 409:
                logger.info("K8s Job %s already exists, re-attaching", job_name)
            else:
                raise

    def create_session_analyzer_job(
        self,
        session_id: str,
        iteration_index: int,
        repo_url: str,
        branch: str,
        instruction: str,
        num_proposals: int,
        selected_proposal_index: int | None = None,
    ) -> str:
        """Create a K8s Job for session-based analysis."""
        job_name = f"ui-worker-{session_id[:12]}-iter{iteration_index}-analyze"
        labels = {
            "app": "ui-recommender",
            "component": "worker",
            "session-id": session_id[:12],
            "iteration": str(iteration_index),
            "mode": "analyze",
        }
        env_vars = [
            client.V1EnvVar(name="SESSION_ID", value=session_id),
            client.V1EnvVar(name="ITERATION_INDEX", value=str(iteration_index)),
            client.V1EnvVar(name="REPO_URL", value=repo_url),
            client.V1EnvVar(name="BRANCH", value=branch),
            client.V1EnvVar(name="INSTRUCTION", value=instruction),
            client.V1EnvVar(name="NUM_PROPOSALS", value=str(num_proposals)),
        ]
        if selected_proposal_index is not None:
            env_vars.append(
                client.V1EnvVar(name="SELECTED_PROPOSAL_INDEX", value=str(selected_proposal_index))
            )
        container = self._build_session_worker_container("analyze", env_vars)
        job = self._build_session_job_spec(job_name, labels, container)
        self._create_job_idempotent(job_name, job)
        return job_name

    def create_session_implementation_job(
        self,
        session_id: str,
        iteration_index: int,
        repo_url: str,
        branch: str,
        proposal_index: int,
        proposal_plan: str,
        selected_proposal_index: int | None = None,
    ) -> str:
        """Create a K8s Job for session-based implementation."""
        job_name = f"ui-worker-{session_id[:12]}-iter{iteration_index}-impl-{proposal_index}"
        labels = {
            "app": "ui-recommender",
            "component": "worker",
            "session-id": session_id[:12],
            "iteration": str(iteration_index),
            "mode": "implement",
        }
        env_vars = [
            client.V1EnvVar(name="SESSION_ID", value=session_id),
            client.V1EnvVar(name="ITERATION_INDEX", value=str(iteration_index)),
            client.V1EnvVar(name="REPO_URL", value=repo_url),
            client.V1EnvVar(name="BRANCH", value=branch),
            client.V1EnvVar(name="PROPOSAL_INDEX", value=str(proposal_index)),
            client.V1EnvVar(name="PROPOSAL_PLAN", value=proposal_plan),
        ]
        if selected_proposal_index is not None:
            env_vars.append(
                client.V1EnvVar(name="SELECTED_PROPOSAL_INDEX", value=str(selected_proposal_index))
            )
        container = self._build_session_worker_container("implement", env_vars)
        job = self._build_session_job_spec(job_name, labels, container)
        self._create_job_idempotent(job_name, job)
        return job_name

    def create_session_pr_job(
        self,
        session_id: str,
        iteration_index: int,
        repo_url: str,
        branch: str,
        proposal_index: int,
    ) -> str:
        """Create a K8s Job for session-based PR creation."""
        job_name = f"ui-worker-{session_id[:12]}-iter{iteration_index}-pr-{proposal_index}"
        labels = {
            "app": "ui-recommender",
            "component": "worker",
            "session-id": session_id[:12],
            "iteration": str(iteration_index),
            "mode": "createpr",
        }
        env_vars = [
            client.V1EnvVar(name="SESSION_ID", value=session_id),
            client.V1EnvVar(name="ITERATION_INDEX", value=str(iteration_index)),
            client.V1EnvVar(name="REPO_URL", value=repo_url),
            client.V1EnvVar(name="BRANCH", value=branch),
            client.V1EnvVar(name="PROPOSAL_INDEX", value=str(proposal_index)),
            client.V1EnvVar(
                name="GITHUB_TOKEN",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="ui-recommender-secrets",
                        key="github-token",
                    )
                ),
            ),
        ]
        container = self._build_session_worker_container("createpr", env_vars)
        job = self._build_session_job_spec(job_name, labels, container)
        self._create_job_idempotent(job_name, job)
        return job_name

    async def stream_pod_logs(
        self, job_name: str, tail_lines: int = 1000, since_seconds: int | None = None
    ) -> AsyncIterator[str]:
        """Stream logs from a job's pod. Yields log lines as they arrive.

        Args:
            tail_lines: Number of past log lines to include (only used for
                        pods that are still running and since_seconds is not set).
            since_seconds: If set, only return logs newer than this many seconds.
                           Used to avoid replaying old logs on reconnect.
        """
        max_wait = 300  # 5 minutes
        poll_interval = 3
        elapsed = 0

        # Wait for a pod to appear
        pod_name: str | None = None
        sandbox_emitted = False
        while elapsed < max_wait:
            try:
                pods = self.core_v1.list_namespaced_pod(
                    namespace=self.namespace,
                    label_selector=f"job-name={job_name}",
                )
                if pods.items:
                    pod = pods.items[0]
                    pod_name = pod.metadata.name
                    phase = pod.status.phase if pod.status else None
                    if phase in ("Running", "Succeeded", "Failed"):
                        break
                    # Pod exists but not yet running
                    if phase == "Pending" and not sandbox_emitted:
                        yield '@@LOG@@{"phase":"sandbox","message":"Creating: sandbox"}'
                        sandbox_emitted = True
            except ApiException as e:
                logger.warning("Error listing pods for job %s: %s", job_name, e)
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if not pod_name:
            msg = f"Pod not found for job {job_name}"
            yield f'@@LOG@@{{"phase":"waiting","message":"{msg}"}}'
            return

        # Use a queue to bridge the blocking iterator and async generator
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _producer() -> None:
            try:
                loop = asyncio.get_running_loop()

                kwargs: dict = {
                    "name": pod_name,
                    "namespace": self.namespace,
                    "follow": True,
                    "_preload_content": False,
                }
                if since_seconds is not None:
                    kwargs["since_seconds"] = since_seconds
                else:
                    kwargs["tail_lines"] = tail_lines

                resp = await asyncio.to_thread(
                    self.core_v1.read_namespaced_pod_log,
                    **kwargs,
                )

                def _iter_lines() -> None:
                    try:
                        for raw_line in resp:
                            if isinstance(raw_line, bytes):
                                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                            else:
                                line = str(raw_line).rstrip("\n")
                            loop.call_soon_threadsafe(queue.put_nowait, line)
                    finally:
                        loop.call_soon_threadsafe(queue.put_nowait, None)

                await asyncio.to_thread(_iter_lines)
            except Exception as e:
                logger.error("Log stream producer error for %s: %s", pod_name, e)
                await queue.put(None)

        producer_task = asyncio.create_task(_producer())
        try:
            while True:
                line = await queue.get()
                if line is None:
                    break
                yield line
        finally:
            producer_task.cancel()

    def delete_job(self, job_name: str) -> None:
        """Delete a completed job and its pods."""
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(propagation_policy="Foreground"),
            )
            logger.info("Deleted K8s Job: %s", job_name)
        except ApiException as e:
            logger.warning("Failed to delete K8s Job %s: %s", job_name, e)
