import json
import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class S3Client:
    """S3-compatible artifact storage (works with AWS S3 and MinIO)."""

    def __init__(self) -> None:
        settings = get_settings()
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": settings.S3_REGION,
            "config": Config(signature_version="s3v4"),
        }
        # MinIO / custom endpoint
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
            kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY
            kwargs["aws_secret_access_key"] = settings.S3_SECRET_KEY
        self.client = boto3.client(**kwargs)
        self.bucket = settings.S3_BUCKET

    def _ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist (for local MinIO)."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            logger.info("Creating S3 bucket: %s", self.bucket)
            self.client.create_bucket(Bucket=self.bucket)

    # ── Key builders ──

    @staticmethod
    def before_screenshot_key(session_id: str, iteration_index: int) -> str:
        return f"sessions/{session_id}/iterations/{iteration_index}/before.png"

    @staticmethod
    def proposals_json_key(session_id: str, iteration_index: int) -> str:
        return f"sessions/{session_id}/iterations/{iteration_index}/proposals.json"

    @staticmethod
    def after_screenshot_key(session_id: str, iteration_index: int, proposal_index: int) -> str:
        base = f"sessions/{session_id}/iterations/{iteration_index}"
        return f"{base}/proposals/{proposal_index}/after.png"

    @staticmethod
    def diff_key(session_id: str, iteration_index: int, proposal_index: int) -> str:
        base = f"sessions/{session_id}/iterations/{iteration_index}"
        return f"{base}/proposals/{proposal_index}/changes.diff"

    @staticmethod
    def plan_key(session_id: str, iteration_index: int, proposal_index: int) -> str:
        base = f"sessions/{session_id}/iterations/{iteration_index}"
        return f"{base}/proposals/{proposal_index}/plan.json"

    @staticmethod
    def pr_url_key(session_id: str, iteration_index: int, proposal_index: int) -> str:
        base = f"sessions/{session_id}/iterations/{iteration_index}"
        return f"{base}/proposals/{proposal_index}/pr_url.txt"

    # ── Read / Write ──

    def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        logger.info("Uploaded %s (%d bytes)", key, len(data))

    def upload_text(self, key: str, text: str) -> None:
        self.upload_bytes(key, text.encode("utf-8"), content_type="text/plain")

    def upload_json(self, key: str, obj: Any) -> None:
        self.upload_bytes(
            key,
            json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )

    def download_bytes(self, key: str) -> bytes | None:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            body: bytes = resp["Body"].read()
            return body
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def download_text(self, key: str) -> str | None:
        data = self.download_bytes(key)
        return data.decode("utf-8") if data else None

    def download_json(self, key: str) -> Any | None:
        text = self.download_text(key)
        if text is None:
            return None
        return json.loads(text)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a presigned URL for direct access (optional future use)."""
        try:
            url: str = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError:
            return None

    # ── High-level artifact accessors ──

    def get_diff(self, session_id: str, iteration_index: int, proposal_index: int) -> str | None:
        return self.download_text(self.diff_key(session_id, iteration_index, proposal_index))

    def get_before_screenshot(self, session_id: str, iteration_index: int) -> bytes | None:
        return self.download_bytes(self.before_screenshot_key(session_id, iteration_index))

    def get_after_screenshot(
        self, session_id: str, iteration_index: int, proposal_index: int
    ) -> bytes | None:
        return self.download_bytes(
            self.after_screenshot_key(session_id, iteration_index, proposal_index)
        )
