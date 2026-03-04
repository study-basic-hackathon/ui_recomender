#!/usr/bin/env python3
"""Implementation Worker: Clones repo, implements a design proposal via Claude Agent SDK, takes after screenshot.

Session-based: Reads/writes all artifacts via S3. No push, no hostPath, no stdout embedding.
Generates cumulative patches (base_branch → all changes squashed into one format-patch).
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, query, AssistantMessage, TextBlock, ToolUseBlock
from claude_agent_sdk.types import StreamEvent


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
        emit_log(phase, f"Reading: {params.get('file_path', '?')}")
    elif tool_name in ("Write", "Edit"):
        emit_log(phase, f"Editing: {params.get('file_path', '?')}")
    elif tool_name == "Bash":
        cmd = params.get("command", "?")
        emit_log(phase, f"Running: {cmd[:100]}")
    elif tool_name in ("Glob", "Grep"):
        emit_log(phase, f"Searching: {params.get('pattern', '?')}")


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


async def implement_changes(repo_dir: str, proposal_plan: str) -> None:
    """Use Claude Agent SDK to implement the design proposal."""
    prompt = f"""You are implementing UI changes to a web application located at {repo_dir}.

Here is the specific design proposal to implement:

{proposal_plan}

- Implement all the changes described in the plan
- All file modifications must be correct and complete
- Follow existing code conventions and patterns
- Do not leave any TODO comments or incomplete implementations
"""

    current_tool = None
    tool_input_chunks = ""

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=40,
            max_budget_usd=3.0,
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
                    _emit_tool_detail("implementing", current_tool, tool_input_chunks)
                current_tool = None
                tool_input_chunks = ""
            continue

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    emit_log("implementing", block.text[:200], detail=block.text)
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail("implementing", block.name, json.dumps(block.input))


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
                    emit_log(phase, block.text[:200], detail=block.text)
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail(phase, block.name, json.dumps(block.input))


async def launch_and_screenshot(repo_dir: str, screenshot_output: str) -> None:
    """Launch dev server and take screenshot in a single session.

    Uses ClaudeSDKClient to keep the same conversation context across
    two query() calls so the agent remembers the dev server URL.
    """
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Bash", "Glob", "Grep"],
        cwd=repo_dir,
        max_turns=20,
        max_budget_usd=1.0,
        include_partial_messages=True,
    )

    async with ClaudeSDKClient(options=options) as client:
        # Phase 1: install deps + start dev server
        emit_log("launching", "Launching project")
        await client.query(f"""You need to launch the web application at {repo_dir}.

Follow these steps:
1. Investigate how to start the dev server (check package.json scripts, README, etc.)
2. Install the project's dependencies if needed (e.g. `npm install` in the project directory)
3. Start the dev server in the background using Bash (e.g. `npm run dev &` or whatever is appropriate)
4. Wait for the server to become ready (poll with curl until it responds)

IMPORTANT: Make sure the dev server is running and responding before finishing.
""")
        await _process_messages(client, "launching")

        # Phase 2: take screenshot (same session, so dev server URL is remembered)
        emit_log("screenshot", "Taking after screenshot")
        await client.query(f"""Now take a screenshot of the running application.

You already know the dev server URL from the previous step. Use it to take a screenshot:
1. Run: `node /usr/local/bin/take-screenshot.mjs <server_url> {screenshot_output}`
   where <server_url> is the URL the dev server is listening on
2. Verify the screenshot file was created at {screenshot_output}

NOTE: Playwright and Chromium are pre-installed globally in this container. Do NOT install playwright or run `npx playwright install`. Just run `node /usr/local/bin/take-screenshot.mjs <url> <output>` directly.
""")
        await _process_messages(client, "screenshot")


async def main() -> None:
    # Read environment variables
    session_id = os.environ["SESSION_ID"]
    iteration_index = int(os.environ["ITERATION_INDEX"])
    repo_url = os.environ["REPO_URL"]
    branch = os.environ.get("BRANCH", "main")
    proposal_index = os.environ["PROPOSAL_INDEX"]
    selected_proposal_index = os.environ.get("SELECTED_PROPOSAL_INDEX")

    bucket = os.environ["S3_BUCKET"]
    s3 = get_s3_client()
    tmp_dir = "/tmp/artifacts"
    repo_dir = "/workspace/repo"
    os.makedirs(tmp_dir, exist_ok=True)

    s3_prefix = (
        f"sessions/{session_id}/iterations/{iteration_index}"
        f"/proposals/{proposal_index}"
    )

    # Step 1: Download proposal plan from S3
    plan_key = f"{s3_prefix}/plan.json"
    local_plan = f"{tmp_dir}/plan.json"
    emit_log("cloning", f"Downloading plan from S3: {plan_key}")
    if s3_download(s3, bucket, plan_key, local_plan):
        proposal_plan = Path(local_plan).read_text()
    else:
        # Fallback to env var (for backward compat during transition)
        proposal_plan = os.environ.get("PROPOSAL_PLAN", "")

    if not proposal_plan:
        print("Error: No proposal plan provided", file=sys.stderr)
        sys.exit(1)

    # Step 2: Clone repository
    emit_log("cloning", "Cloning repository")
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, repo_dir],
        check=True,
    )

    # Step 2.5: Apply cumulative patch from previous iteration (if iter > 0)
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

    # Step 3: Create local branch and implement the proposal
    branch_name = f"local/session-{session_id[:8]}-iter{iteration_index}-prop{proposal_index}"
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_dir, check=True)
    emit_log("implementing", f"Created local branch: {branch_name}")

    screenshot_path = f"{tmp_dir}/after.png"
    emit_log("implementing", "Implementing design proposal")
    await implement_changes(repo_dir, proposal_plan)

    # Launch + screenshot in a single session (shares dev server URL context)
    await launch_and_screenshot(repo_dir, screenshot_path)

    # Step 4: Generate cumulative patch (squash everything since base_branch)
    emit_log("uploading", "Generating cumulative patch")
    # Parse proposal plan to get title for commit message
    try:
        plan_data = json.loads(proposal_plan)
        commit_title = plan_data.get("title", f"variant-{proposal_index}")
    except (json.JSONDecodeError, AttributeError):
        commit_title = f"variant-{proposal_index}"

    # Stage all changes
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
    # Squash all changes into a single commit relative to base_branch
    subprocess.run(
        ["git", "reset", "--soft", f"origin/{branch}"],
        cwd=repo_dir,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"feat: {commit_title}"],
        cwd=repo_dir,
        check=True,
    )
    # Generate format-patch (cumulative: base_branch → HEAD)
    patch_result = subprocess.run(
        ["git", "format-patch", "-1", "HEAD", "--stdout"],
        capture_output=True, text=True, cwd=repo_dir,
        check=True,
    )
    local_diff = f"{tmp_dir}/changes.diff"
    with open(local_diff, "w") as f:
        f.write(patch_result.stdout)

    # Step 5: Upload results to S3
    emit_log("uploading", "Uploading results to S3")

    # Upload after screenshot
    if Path(screenshot_path).exists():
        s3_upload_file(
            s3, bucket,
            f"{s3_prefix}/after.png",
            screenshot_path,
            content_type="image/png",
        )

    # Upload cumulative patch
    s3_upload_text(
        s3, bucket,
        f"{s3_prefix}/changes.diff",
        patch_result.stdout,
        content_type="text/plain",
    )

    emit_log("completed", "Implementation complete")


if __name__ == "__main__":
    asyncio.run(main())
