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
from pathlib import Path

import boto3
from botocore.config import Config
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, query, AssistantMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import StreamEvent

PLAYWRIGHT_MCP_SERVERS = {
    "playwright": {
        "command": "npx",
        "args": ["@playwright/mcp@0.0.68", "--headless", "--browser", "chromium", "--viewport-size", "1280x800"],
    },
    "playwright_mobile": {
        "command": "npx",
        "args": ["@playwright/mcp@0.0.68", "--headless", "--browser", "chromium", "--device", "iPhone 15"],
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
    elif tool_name == "Bash":
        cmd = params.get("command", "?").replace("/workspace/repo/", "").replace("/workspace/repo", ".")
        emit_log(phase, f"Running: {cmd[:100]}")


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


async def _process_messages(client: ClaudeSDKClient, phase: str) -> None:
    """Process messages from ClaudeSDKClient, emitting logs for a given phase."""
    current_tool = None
    tool_input_chunks = ""

    async for msg in client.receive_response():
        if isinstance(msg, StreamEvent):
            event = msg.event
            etype = event.get("type")
            if etype == "content_block_start":
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    current_tool = content_block.get("name")
                    tool_input_chunks = ""
            elif etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "input_json_delta":
                    tool_input_chunks += delta.get("partial_json", "")
            elif etype == "content_block_stop":
                if current_tool and tool_input_chunks:
                    _emit_tool_detail(phase, current_tool, tool_input_chunks)
                current_tool = None
                tool_input_chunks = ""
            continue

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text = block.text.strip()
                    if text.startswith("Browser") or text.startswith("Searching"):
                        continue
                    emit_log(phase, text[:200], detail=block.text)
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail(phase, block.name, json.dumps(block.input))


async def launch_and_screenshot(repo_dir: str, screenshot_output: str, device_type: str = "desktop") -> None:
    """Launch dev server and take screenshot in a single session.

    Uses ClaudeSDKClient to keep the same conversation context across
    two query() calls so the agent remembers the dev server URL.
    """
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Bash", "Glob", "Grep"] + PLAYWRIGHT_MCP_TOOLS,
        mcp_servers=PLAYWRIGHT_MCP_SERVERS,
        cwd=repo_dir,
        max_turns=20,
        max_budget_usd=1.0,
        include_partial_messages=True,
    )

    async with ClaudeSDKClient(options=options) as client:
        # Phase 1: install deps + start dev server
        emit_log("launching", "Launching project")
        await client.query("""You need to launch the web application.

Follow these steps:
1. Investigate how to start the dev server (check package.json scripts, README, etc.)
2. Install the project's dependencies if needed (e.g. `npm install` in the project directory)
3. Start the dev server in the background using Bash (e.g. `npm run dev &` or whatever is appropriate)
4. Wait for the server to become ready (poll with curl until it responds)

IMPORTANT:
- Playwright and Chromium are already installed globally. Do NOT run `npx playwright install` or any Playwright installation commands.
- Only install the PROJECT's dependencies (e.g. `npm install` in the project directory).
- Make sure the dev server is running and responding before finishing.
""")
        await _process_messages(client, "launching")

        # Phase 2: take screenshot (same session, so dev server URL is remembered)
        emit_log("screenshot", "Taking before screenshot")
        device = "playwright_mobile" if device_type == "mobile" else "playwright"
        await client.query(f"""Now take a screenshot of the running application.

You already know the dev server URL from the previous step.

Use the **{device}** browser tools (mcp__{device}__*) to take the screenshot.

Steps:
1. Use mcp__{device}__browser_navigate to open the dev server URL
2. Use mcp__{device}__browser_wait_for to wait for the page to fully load
3. Use mcp__{device}__browser_take_screenshot to capture the viewport and save to {screenshot_output}

IMPORTANT:
- Do NOT use fullPage. Capture only what the user actually sees in the viewport.
- If a specific element needs to be visible, use mcp__{device}__browser_evaluate to scrollIntoView first.
""")
        await _process_messages(client, "screenshot")


def _extract_proposals_json(collected_text: list[str]) -> dict:
    """Extract proposals JSON from Claude Agent output, trying multiple strategies.

    Returns a dict with "device_type" and "proposals" keys.
    """

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
                return data
            if isinstance(data, list):
                return {"device_type": "desktop", "proposals": data}
        except json.JSONDecodeError:
            pass

        # If block contains JSON embedded after prose, find the first '{' and try parsing from there
        brace_idx = text.find('{"proposals"')
        if brace_idx == -1:
            brace_idx = text.find('{"device_type"')
        if brace_idx == -1:
            brace_idx = text.find("{\n")
        if brace_idx >= 0:
            candidate = text[brace_idx:]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "proposals" in data:
                    return data
            except json.JSONDecodeError:
                pass

    # Strategy 2: Find JSON object in concatenated text and use JSONDecoder to parse
    full_text = "\n".join(collected_text)
    decoder = json.JSONDecoder()
    for marker in ['{"device_type"', '{"proposals"']:
        idx = full_text.find(marker)
        if idx >= 0:
            try:
                data, _ = decoder.raw_decode(full_text, idx)
                if isinstance(data, dict) and "proposals" in data:
                    return data
            except json.JSONDecodeError:
                pass

    # Strategy 3: Extract from markdown code blocks in full text
    for pattern in [r'```json\s*(.*?)```', r'```\s*(.*?)```']:
        m = re.search(pattern, full_text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1).strip())
                if isinstance(data, dict) and "proposals" in data:
                    return data
                if isinstance(data, list):
                    return {"device_type": "desktop", "proposals": data}
            except json.JSONDecodeError:
                continue

    print("Failed to parse proposals JSON from all strategies", file=sys.stderr)
    print(f"Collected {len(collected_text)} text blocks", file=sys.stderr)
    for i, t in enumerate(collected_text):
        print(f"Block {i}: {t[:200]}", file=sys.stderr)

    return {"device_type": "desktop", "proposals": []}


async def generate_proposals(
    repo_dir: str, instruction: str, num_proposals: int
) -> dict:
    """Use Claude Agent SDK to analyze the repo and generate design proposals.

    Returns a dict with "device_type" and "proposals" keys.
    """
    prompt = f"""You are a UI/UX design expert analyzing a web application repository.
The user wants the following UI changes:

{instruction}

## Your Task

1. Analyze the codebase using the available tools (Read, Glob, Grep) to understand the project structure, framework, and relevant files.
2. Determine the project's target platform:
   - Check package.json for mobile frameworks (react-native, @capacitor, @ionic, expo)
   - Check HTML viewport meta tag and CSS media queries
   - If the project targets mobile or is mobile-first → set device_type to "mobile"
   - Otherwise → set device_type to "desktop"
3. Generate exactly {num_proposals} different design proposals, each taking a meaningfully different approach.

## Output Format

IMPORTANT: After your analysis, you MUST output EXACTLY ONE valid JSON object as your FINAL message.
Do not include any text before or after the JSON. Do not wrap it in markdown code blocks.
Include "device_type" at the top level of the JSON.
The JSON must follow this exact structure:

{{
  "device_type": "desktop|mobile",
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
                    text = block.text.strip()
                    if text.startswith("Browser") or text.startswith("Searching"):
                        continue
                    emit_log("analyzing", text[:200], detail=block.text)
                    collected_text.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail("analyzing", block.name, json.dumps(block.input))

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

    # Step 2: Code analysis + device detection + proposal generation (no browser needed)
    emit_log("analyzing", "Generating design proposals")
    try:
        result = await generate_proposals(repo_dir, instruction, num_proposals)
    except Exception as e:
        emit_log("analyzing", f"Analysis interrupted: {e}", detail=str(e))
        result = {"device_type": "desktop", "proposals": []}

    proposals = result.get("proposals", [])
    device_type = result.get("device_type", "desktop")
    if isinstance(device_type, str):
        device_type = device_type.lower()
    if device_type not in ("desktop", "mobile"):
        device_type = "desktop"
    emit_log("analyzing", f"Generated {len(proposals)} proposals (device: {device_type})")

    # Step 3: Launch dev server + take before screenshot (with determined device_type)
    before_path = f"{tmp_dir}/before.png"
    await launch_and_screenshot(repo_dir, before_path, device_type=device_type)

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

    # Upload proposals.json (includes device_type)
    proposals_data = {"device_type": device_type, "proposals": proposals}
    s3_upload_text(
        s3, bucket,
        f"{s3_prefix}/proposals.json",
        json.dumps(proposals_data, ensure_ascii=False, indent=2),
        content_type="application/json",
    )

    emit_log("completed", "Analysis complete")


if __name__ == "__main__":
    asyncio.run(main())
