#!/usr/bin/env python3
"""Analyzer Worker: Clones repo, takes before screenshot, generates design proposals via Claude Agent SDK.

Session-based: Reads/writes all artifacts via S3. No hostPath, no stdout embedding.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import boto3
from botocore.config import Config
from claude_agent_sdk import ClaudeAgentOptions, query, AssistantMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import StreamEvent


def emit_log(phase: str, message: str, detail: str | None = None) -> None:
    entry = {
        "phase": phase,
        "message": message,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if detail:
        entry["detail"] = detail
    print(f"@@LOG@@{json.dumps(entry, ensure_ascii=False)}", flush=True)


def _emit_tool_detail(phase: str, tool_name: str, raw_input: str) -> None:
    """Parse tool input JSON and emit a human-readable log line."""
    try:
        params = json.loads(raw_input)
    except json.JSONDecodeError:
        emit_log(phase, f"Using tool: {tool_name}")
        return

    if tool_name == "Read":
        emit_log(phase, f"Reading: {params.get('file_path', '?')}")
    elif tool_name in ("Write", "Edit"):
        emit_log(phase, f"Editing: {params.get('file_path', '?')}")
    elif tool_name == "Bash":
        cmd = params.get("command", "?")
        emit_log(phase, f"Running: {cmd[:100]}")
    elif tool_name in ("Glob", "Grep"):
        emit_log(phase, f"Searching: {params.get('pattern', '?')}")
    else:
        emit_log(phase, f"Using tool: {tool_name}")


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


def s3_upload_file(s3, bucket, key, local_path, content_type="application/octet-stream"):
    for attempt in range(3):
        try:
            s3.upload_file(
                local_path, bucket, key,
                ExtraArgs={"ContentType": content_type},
            )
            print(f"Uploaded {key}")
            return
        except Exception as e:
            print(f"S3 upload attempt {attempt + 1} failed for {key}: {e}", file=sys.stderr)
            if attempt == 2:
                raise


def s3_upload_text(s3, bucket, key, text, content_type="text/plain"):
    for attempt in range(3):
        try:
            s3.put_object(
                Bucket=bucket, Key=key,
                Body=text.encode("utf-8"), ContentType=content_type,
            )
            print(f"Uploaded {key}")
            return
        except Exception as e:
            print(f"S3 upload attempt {attempt + 1} failed for {key}: {e}", file=sys.stderr)
            if attempt == 2:
                raise


async def take_before_screenshot(repo_dir: str, screenshot_output: str) -> None:
    """Use Claude Agent SDK to start dev server and take a before screenshot."""
    prompt = f"""You need to start the dev server for the web application at {repo_dir} and take a screenshot.

Follow these steps:
1. Investigate how to start the dev server (check package.json scripts, README, etc.)
2. Install dependencies if needed
3. Start the dev server in the background using Bash (e.g. `npm run dev &` or whatever is appropriate)
4. Wait for the server to become ready (poll with curl until it responds)
5. Once the server is ready, take a screenshot by running:
   `node /usr/local/bin/take-screenshot.mjs <server_url> {screenshot_output}`
   where <server_url> is the URL the dev server is listening on (e.g. http://localhost:5173)
6. Verify the screenshot file was created at {screenshot_output}

IMPORTANT: The screenshot is critical. Do your best to get the dev server running and take the screenshot.
"""

    current_tool = None
    tool_input_chunks = ""

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Bash", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=20,
            max_budget_usd=1.0,
            include_partial_messages=True,
        ),
    ):
        if isinstance(msg, StreamEvent):
            event = msg.event
            etype = event.get("type")
            if etype == "content_block_start":
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    current_tool = content_block.get("name")
                    tool_input_chunks = ""
                    emit_log("screenshot", f"Tool: {current_tool}")
            elif etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "input_json_delta":
                    tool_input_chunks += delta.get("partial_json", "")
            elif etype == "content_block_stop":
                if current_tool and tool_input_chunks:
                    _emit_tool_detail("screenshot", current_tool, tool_input_chunks)
                current_tool = None
                tool_input_chunks = ""
            continue

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    emit_log("screenshot", block.text[:200], detail=block.text)
                    print(f"Screenshot Agent: {block.text[:200]}")
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail("screenshot", block.name, json.dumps(block.input))
                    print(f"Screenshot Tool: {block.name}")


def _extract_proposals_json(collected_text: list[str]) -> list[dict]:
    """Extract proposals JSON from Claude Agent output, trying multiple strategies."""

    # Strategy 1: Try each text block from the end (last output is most likely the JSON)
    for text in reversed(collected_text):
        text = text.strip()
        if not text:
            continue
        # Strip markdown code block wrapping
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        # Try parsing the whole block first
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "proposals" in data:
                return data["proposals"]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        # If block contains JSON embedded after prose, find the first '{' and try parsing from there
        brace_idx = text.find('{"proposals"')
        if brace_idx == -1:
            brace_idx = text.find("{\n")
        if brace_idx >= 0:
            candidate = text[brace_idx:]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "proposals" in data:
                    return data["proposals"]
            except json.JSONDecodeError:
                pass

    # Strategy 2: Find {"proposals" in concatenated text and use JSONDecoder to parse
    full_text = "\n".join(collected_text)
    decoder = json.JSONDecoder()
    idx = full_text.find('{"proposals"')
    if idx >= 0:
        try:
            data, _ = decoder.raw_decode(full_text, idx)
            if isinstance(data, dict) and "proposals" in data:
                return data["proposals"]
        except json.JSONDecodeError:
            pass

    # Strategy 3: Extract from markdown code blocks in full text
    for pattern in [r'```json\s*(.*?)```', r'```\s*(.*?)```']:
        m = re.search(pattern, full_text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1).strip())
                if isinstance(data, dict) and "proposals" in data:
                    return data["proposals"]
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue

    print("Failed to parse proposals JSON from all strategies", file=sys.stderr)
    print(f"Collected {len(collected_text)} text blocks", file=sys.stderr)
    for i, t in enumerate(collected_text):
        print(f"Block {i}: {t[:200]}", file=sys.stderr)

    return []


async def generate_proposals(
    repo_dir: str, instruction: str, num_proposals: int
) -> list[dict]:
    """Use Claude Agent SDK to analyze the repo and generate design proposals."""
    prompt = f"""You are a UI/UX design expert analyzing a web application repository.
The user wants the following UI changes:

{instruction}

## Your Task

1. First, analyze the codebase using the available tools (Read, Glob, Grep) to understand the project structure, framework, and relevant files.
2. After sufficient analysis, generate exactly {num_proposals} different design proposals.
3. Each proposal should take a meaningfully different approach.

## Output Format

IMPORTANT: After your analysis, you MUST output EXACTLY ONE valid JSON object as your FINAL message.
Do not include any text before or after the JSON. Do not wrap it in markdown code blocks.
The JSON must follow this exact structure:

{{
  "proposals": [
    {{
      "title": "Short title (under 50 chars)",
      "concept": "2-3 sentence description of the approach",
      "plan": ["Step 1: ...", "Step 2: ...", "..."],
      "files": [{{"path": "relative/path/to/file", "reason": "Why this file needs changes"}}],
      "complexity": "low|medium|high"
    }}
  ]
}}

Remember: The JSON output is the MOST IMPORTANT part. Even if your analysis is incomplete, you MUST output the JSON before finishing.
"""

    collected_text = []
    current_tool = None
    tool_input_chunks = ""

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=30,
            include_partial_messages=True,
        ),
    ):
        if isinstance(msg, StreamEvent):
            event = msg.event
            etype = event.get("type")
            if etype == "content_block_start":
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    current_tool = content_block.get("name")
                    tool_input_chunks = ""
                    emit_log("analyzing", f"Tool: {current_tool}")
            elif etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "input_json_delta":
                    tool_input_chunks += delta.get("partial_json", "")
            elif etype == "content_block_stop":
                if current_tool and tool_input_chunks:
                    _emit_tool_detail("analyzing", current_tool, tool_input_chunks)
                current_tool = None
                tool_input_chunks = ""
            continue

        # Collect text content from assistant messages
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    emit_log("analyzing", block.text[:200], detail=block.text)
                    collected_text.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail("analyzing", block.name, json.dumps(block.input))
                    print(f"Analyze Tool: {block.name}")

    return _extract_proposals_json(collected_text)


async def main() -> None:
    # Read environment variables
    session_id = os.environ["SESSION_ID"]
    iteration_index = int(os.environ["ITERATION_INDEX"])
    repo_url = os.environ["REPO_URL"]
    branch = os.environ.get("BRANCH", "main")
    instruction = os.environ["INSTRUCTION"]
    num_proposals = int(os.environ.get("NUM_PROPOSALS", "3"))
    selected_proposal_index = os.environ.get("SELECTED_PROPOSAL_INDEX")

    bucket = os.environ["S3_BUCKET"]
    s3 = get_s3_client()
    tmp_dir = "/tmp/artifacts"
    repo_dir = "/workspace/repo"
    os.makedirs(tmp_dir, exist_ok=True)

    s3_prefix = f"sessions/{session_id}/iterations/{iteration_index}"

    # Step 1: Clone repository
    emit_log("cloning", "Cloning repository")
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, repo_dir],
        check=True,
    )

    # Step 1.5: Apply cumulative patch from previous iteration (if iter > 0)
    if iteration_index > 0 and selected_proposal_index is not None:
        prev_iter = iteration_index - 1
        patch_key = (
            f"sessions/{session_id}/iterations/{prev_iter}"
            f"/proposals/{selected_proposal_index}/changes.diff"
        )
        local_patch = f"{tmp_dir}/parent.diff"
        emit_log("patching", f"Downloading patch from S3: {patch_key}")
        if s3_download(s3, bucket, patch_key, local_patch):
            emit_log("patching", "Applying cumulative patch")
            result = subprocess.run(
                ["git", "am", "--3way", local_patch],
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"git am failed: {result.stderr}", file=sys.stderr)
                print("Falling back to git apply...")
                subprocess.run(
                    ["git", "am", "--abort"], cwd=repo_dir, capture_output=True
                )
                subprocess.run(
                    ["git", "apply", "--3way", local_patch],
                    cwd=repo_dir,
                    check=True,
                )
                subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
                subprocess.run(
                    ["git", "commit", "-m", "apply base patch"],
                    cwd=repo_dir,
                    check=True,
                )
            emit_log("patching", "Cumulative patch applied successfully")
        else:
            print(
                f"WARNING: Patch not found at s3://{bucket}/{patch_key}",
                file=sys.stderr,
            )

    # Step 2: Take before screenshot
    emit_log("screenshot", "Taking before screenshot")
    before_path = f"{tmp_dir}/before.png"
    await take_before_screenshot(repo_dir, before_path)

    # Step 3: Generate design proposals via Claude Agent SDK
    emit_log("analyzing", "Generating design proposals")
    proposals = await generate_proposals(repo_dir, instruction, num_proposals)
    emit_log("analyzing", f"Generated {len(proposals)} proposals")

    # Step 4: Upload results to S3
    emit_log("uploading", "Uploading results to S3")

    # Upload before screenshot
    if Path(before_path).exists():
        s3_upload_file(
            s3, bucket,
            f"{s3_prefix}/before.png",
            before_path,
            content_type="image/png",
        )

    # Upload proposals.json
    proposals_data = {"proposals": proposals}
    s3_upload_text(
        s3, bucket,
        f"{s3_prefix}/proposals.json",
        json.dumps(proposals_data, ensure_ascii=False, indent=2),
        content_type="application/json",
    )

    emit_log("completed", "Analysis complete")


if __name__ == "__main__":
    asyncio.run(main())
