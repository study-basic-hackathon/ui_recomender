"""Shared utilities for analyze and implement worker scripts.

Centralizes logging, S3, and stream processing to prevent divergence.
"""

import json
import os
import sys

import boto3
from botocore.config import Config
from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import StreamEvent


PLAYWRIGHT_MCP_SERVERS = {
    "playwright": {
        "command": "npx",
        "args": [
            "@playwright/mcp@0.0.68",
            "--headless",
            "--browser",
            "chromium",
            "--viewport-size",
            "1280x800",
        ],
    },
    "playwright_mobile": {
        "command": "npx",
        "args": [
            "@playwright/mcp@0.0.68",
            "--headless",
            "--browser",
            "chromium",
            "--device",
            "iPhone 15",
        ],
    },
}

PLAYWRIGHT_MCP_TOOLS = [
    "mcp__playwright__browser_navigate",
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_take_screenshot",
    "mcp__playwright__browser_wait_for",
    "mcp__playwright__browser_evaluate",
    "mcp__playwright__browser_console_messages",
    "mcp__playwright_mobile__browser_navigate",
    "mcp__playwright_mobile__browser_snapshot",
    "mcp__playwright_mobile__browser_take_screenshot",
    "mcp__playwright_mobile__browser_wait_for",
    "mcp__playwright_mobile__browser_evaluate",
    "mcp__playwright_mobile__browser_console_messages",
]


def emit_log(phase: str, message: str, detail: str | None = None) -> None:
    entry = {
        "phase": phase,
        "message": message,
    }
    if detail:
        entry["detail"] = detail
    print(f"@@LOG@@{json.dumps(entry, ensure_ascii=False)}", flush=True)


def _emit_tool_detail(phase: str, tool_name: str, raw_input: str) -> None:
    """Parse tool input JSON and emit a human-readable log line."""
    try:
        params = json.loads(raw_input)
    except json.JSONDecodeError:
        return

    if tool_name == "Read":
        path = params.get("file_path", "?").replace("/workspace/repo/", "")
        emit_log(phase, f"Reading: {path}")
    elif tool_name in ("Write", "Edit"):
        path = params.get("file_path", "?").replace("/workspace/repo/", "")
        emit_log(phase, f"Editing: {path}")


async def process_messages(client: ClaudeSDKClient, phase: str) -> None:
    """Process messages from ClaudeSDKClient, emitting logs for a given phase."""
    async for msg in client.receive_response():
        if isinstance(msg, StreamEvent):
            continue  # Skip streaming events; logs emitted from AssistantMessage only

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text = block.text.strip()
                    if text.startswith("Browser") or text.startswith("Searching"):
                        continue
                    emit_log(phase, f"Thinking: {text[:200]}", detail=block.text)
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail(phase, block.name, json.dumps(block.input))


def get_s3_client():
    kwargs = {
        "service_name": "s3",
        "region_name": os.environ.get("S3_REGION", "us-east-1"),
        "config": Config(signature_version="s3v4"),
    }
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = os.environ.get("S3_ACCESS_KEY", "minioadmin")
        kwargs["aws_secret_access_key"] = os.environ.get("S3_SECRET_KEY", "minioadmin")
    return boto3.client(**kwargs)


def s3_download(s3, bucket, key, local_path):
    try:
        s3.download_file(bucket, key, local_path)
        return True
    except Exception as e:
        print(f"S3 download failed for {key}: {e}", file=sys.stderr)
        return False


def s3_upload_file(
    s3, bucket, key, local_path, content_type="application/octet-stream"
):
    for attempt in range(3):
        try:
            s3.upload_file(
                local_path,
                bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
            print(f"Uploaded {key}")
            return
        except Exception as e:
            print(
                f"S3 upload attempt {attempt + 1} failed for {key}: {e}",
                file=sys.stderr,
            )
            if attempt == 2:
                raise


def s3_upload_text(s3, bucket, key, text, content_type="text/plain"):
    for attempt in range(3):
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=text.encode("utf-8"),
                ContentType=content_type,
            )
            print(f"Uploaded {key}")
            return
        except Exception as e:
            print(
                f"S3 upload attempt {attempt + 1} failed for {key}: {e}",
                file=sys.stderr,
            )
            if attempt == 2:
                raise
