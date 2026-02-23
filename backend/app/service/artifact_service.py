import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Marker pattern used by workers to embed artifacts in stdout
_ARTIFACT_PATTERN = re.compile(
    r"===ARTIFACT:(?P<name>[^:]+):START===\n(?P<content>.*?)===ARTIFACT:(?P=name):END===",
    re.DOTALL,
)


class ArtifactService:
    """Manages artifacts produced by worker pods.

    Artifacts are extracted from pod logs (stdout markers) and cached
    to the local filesystem. This approach is portable across any K8s
    environment without requiring shared volumes or cloud storage.
    """

    def __init__(self) -> None:
        self.base_dir = Path(get_settings().ARTIFACTS_DIR)

    def extract_artifacts_from_logs(self, job_id: str, logs: str) -> dict[str, str]:
        """Extract artifacts embedded in pod logs and save them locally.

        Returns a dict of artifact_name -> local_path.
        """
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        saved = {}

        for match in _ARTIFACT_PATTERN.finditer(logs):
            name = match.group("name")
            content = match.group("content").strip()

            if name.endswith(".png"):
                # Binary file encoded as base64
                try:
                    data = base64.b64decode(content)
                    path = job_dir / name
                    path.write_bytes(data)
                    saved[name] = str(path)
                    logger.info("Extracted binary artifact %s for job %s", name, job_id)
                except Exception as e:
                    logger.error("Failed to decode %s for job %s: %s", name, job_id, e)
            else:
                # Text file
                path = job_dir / name
                path.write_text(content)
                saved[name] = str(path)
                logger.info("Extracted text artifact %s for job %s", name, job_id)

        return saved

    def extract_impl_artifacts_from_logs(
        self, job_id: str, proposal_index: int, logs: str
    ) -> dict[str, str]:
        """Extract implementation artifacts and save under proposals/{index}/."""
        proposal_dir = self.base_dir / job_id / "proposals" / str(proposal_index)
        proposal_dir.mkdir(parents=True, exist_ok=True)
        saved = {}

        for match in _ARTIFACT_PATTERN.finditer(logs):
            name = match.group("name")
            content = match.group("content").strip()

            if name.endswith(".png"):
                try:
                    data = base64.b64decode(content)
                    path = proposal_dir / name
                    path.write_bytes(data)
                    saved[name] = str(path)
                    logger.info(
                        "Extracted binary artifact %s for job %s proposal %d",
                        name,
                        job_id,
                        proposal_index,
                    )
                except Exception as e:
                    logger.error("Failed to decode %s: %s", name, e)
            else:
                path = proposal_dir / name
                path.write_text(content)
                saved[name] = str(path)
                logger.info(
                    "Extracted text artifact %s for job %s proposal %d",
                    name,
                    job_id,
                    proposal_index,
                )

        return saved

    def get_before_screenshot_path(self, job_id: str) -> Path | None:
        path = self.base_dir / job_id / "before.png"
        return path if path.exists() else None

    def get_proposals_json(self, job_id: str) -> list[dict[str, Any]] | None:
        """Read proposals.json from local cache."""
        path = self.base_dir / job_id / "proposals.json"
        if not path.exists():
            logger.warning("Proposals file not found for job %s", job_id)
            return None

        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict) and "proposals" in data:
                proposals: list[dict[str, Any]] = data["proposals"]
                return proposals
            if isinstance(data, list):
                return data
            logger.warning("Unexpected proposals format for job %s", job_id)
            return None
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to parse proposals for job %s: %s", job_id, e)
            return None

    def get_after_screenshot_path(self, job_id: str, proposal_index: int) -> Path | None:
        path = self.base_dir / job_id / "proposals" / str(proposal_index) / "after.png"
        return path if path.exists() else None

    def get_diff(self, job_id: str, proposal_index: int) -> str | None:
        path = self.base_dir / job_id / "proposals" / str(proposal_index) / "changes.diff"
        if not path.exists():
            return None
        try:
            return path.read_text()
        except OSError as e:
            logger.error("Failed to read diff: %s", e)
            return None

    def get_pr_url(self, job_id: str, proposal_index: int) -> str | None:
        """Read the PR URL artifact for a proposal."""
        path = self.base_dir / job_id / "proposals" / str(proposal_index) / "pr_url.txt"
        if not path.exists():
            return None
        try:
            return path.read_text().strip()
        except OSError as e:
            logger.error("Failed to read PR URL: %s", e)
            return None

    def write_proposal_plan(self, job_id: str, proposal_index: int, plan_text: str) -> Path:
        """Write proposal plan to a file (used for local reference)."""
        path = self.base_dir / job_id / f"proposal_{proposal_index}_plan.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(plan_text)
        return path
