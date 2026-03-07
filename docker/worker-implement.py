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

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    query,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import StreamEvent
from prompts import LAUNCH_DEV_SERVER_PROMPT, build_screenshot_prompt, build_implement_prompt, build_fix_prompt, SYSTEM_PROMPT, READONLY_SYSTEM_PROMPT
from worker_common import (
    emit_log,
    _emit_tool_detail,
    process_messages,
    get_s3_client,
    s3_download,
    s3_upload_file,
    s3_upload_text,
    PLAYWRIGHT_MCP_SERVERS,
    PLAYWRIGHT_MCP_TOOLS,
)


async def implement_changes(
    repo_dir: str, proposal_plan: str
) -> None:
    """Use Claude Agent SDK to implement the design proposal."""
    # Format proposal_plan for readability (C-2)
    try:
        plan_data = (
            json.loads(proposal_plan)
            if isinstance(proposal_plan, str)
            else proposal_plan
        )
        formatted_plan = (
            f"""User Request: {plan_data.get("instruction", "N/A")}
Title: {plan_data.get("title", "N/A")}
Concept: {plan_data.get("concept", "N/A")}

Steps:
"""
            + "\n".join(
                f"  {i + 1}. {step}" for i, step in enumerate(plan_data.get("plan", []))
            )
            + """

Target files:
"""
            + "\n".join(
                f"  - {f['path']}: {f.get('reason', '')}"
                for f in plan_data.get("files", [])
            )
        )
    except (json.JSONDecodeError, AttributeError, TypeError):
        formatted_plan = str(proposal_plan)

    prompt_text = build_implement_prompt(formatted_plan)

    async for msg in query(
        prompt=prompt_text,
        options=ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=40,
            max_budget_usd=float(os.environ.get("IMPLEMENT_MAX_BUDGET_USD", "3.0")),
            include_partial_messages=True,
            thinking={"type": "adaptive"},
        ),
    ):
        if isinstance(msg, StreamEvent):
            continue  # Skip streaming events; logs emitted from AssistantMessage only

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text = block.text.strip()
                    if text.startswith("Browser") or text.startswith("Searching"):
                        continue
                    emit_log(
                        "implementing", f"Thinking: {text[:200]}", detail=block.text
                    )
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail(
                        "implementing", block.name, json.dumps(block.input)
                    )


async def kill_dev_servers(repo_dir: str) -> None:
    """Kill any lingering dev server processes (frontend and backend)."""
    for pattern in [
        "node",
        "vite",
        "next",
        "uvicorn",
        "gunicorn",
        "flask",
        "manage.py runserver",
    ]:
        subprocess.run(
            ["pkill", "-f", pattern],
            capture_output=True,
        )
    await asyncio.sleep(2)


async def fix_with_claude(
    repo_dir: str, error_message: str, device_type: str = "desktop"
) -> None:
    """Use Claude to diagnose and fix the dev server launch failure."""
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        # Browser tools removed: server is down so browser cannot connect, wasting turns
        mcp_servers=PLAYWRIGHT_MCP_SERVERS,
        cwd=repo_dir,
        max_turns=20,
        max_budget_usd=1.5,
        include_partial_messages=True,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(build_fix_prompt(error_message))
        await process_messages(client,"implementing")


async def launch_and_screenshot(
    repo_dir: str,
    screenshot_output: str,
    device_type: str = "desktop",
    instruction: str = "",
) -> None:
    """Launch dev server and take screenshot in a single session.

    Uses ClaudeSDKClient to keep the same conversation context across
    two query() calls so the agent remembers the dev server URL.
    """
    options = ClaudeAgentOptions(
        system_prompt=READONLY_SYSTEM_PROMPT,
        allowed_tools=["Read", "Bash", "Glob", "Grep"] + PLAYWRIGHT_MCP_TOOLS,
        mcp_servers=PLAYWRIGHT_MCP_SERVERS,
        cwd=repo_dir,
        max_turns=20,
        max_budget_usd=1.0,
        include_partial_messages=True,
    )

    async with ClaudeSDKClient(options=options) as client:
        # Phase 1: install deps + start dev server
        emit_log("launching", "Launching: project")
        await client.query(LAUNCH_DEV_SERVER_PROMPT)
        await process_messages(client,"launching")

        # Phase 2: take screenshot (same session, so dev server URL is remembered)
        emit_log("screenshot", "Taking: after screenshot")
        device = "playwright_mobile" if device_type == "mobile" else "playwright"
        await client.query(build_screenshot_prompt(device, screenshot_output, instruction))
        await process_messages(client,"screenshot")

    # Verify screenshot was actually created
    if not Path(screenshot_output).exists():
        raise RuntimeError(
            f"Screenshot was not created at {screenshot_output}. "
            "The dev server likely failed to start or the screenshot command failed."
        )


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
        f"sessions/{session_id}/iterations/{iteration_index}/proposals/{proposal_index}"
    )

    # Step 1: Download proposal plan from S3
    plan_key = f"{s3_prefix}/plan.json"
    local_plan = f"{tmp_dir}/plan.json"
    emit_log("cloning", f"Downloading plan from S3: {plan_key}")
    device_type = "desktop"
    if s3_download(s3, bucket, plan_key, local_plan):
        raw = Path(local_plan).read_text()
        try:
            plan_data = json.loads(raw)
            # Pass the full plan object (title, concept, plan, files) to implement_changes
            proposal_plan = {
                k: v
                for k, v in plan_data.items()
                if k not in ("device_type", "instruction")
            }
            device_type = plan_data.get("device_type", "desktop")
            instruction = plan_data.get("instruction", "")
            if isinstance(device_type, str):
                device_type = device_type.lower()
            if device_type not in ("desktop", "mobile"):
                device_type = "desktop"
        except json.JSONDecodeError:
            proposal_plan = raw  # backward compat
            instruction = ""
    else:
        # Fallback to env var (for backward compat during transition)
        proposal_plan = os.environ.get("PROPOSAL_PLAN", "")
        instruction = ""
    emit_log("setup", f"Using device type: {device_type}")

    # Log loaded proposal details
    try:
        _plan = (
            json.loads(proposal_plan)
            if isinstance(proposal_plan, str)
            else proposal_plan
        )
        title = _plan.get("title", f"proposal-{proposal_index}")
    except (json.JSONDecodeError, AttributeError):
        title = f"proposal-{proposal_index}"
    emit_log("setup", f"Loaded proposal {proposal_index}: {title}")

    if not proposal_plan:
        print("Error: No proposal plan provided", file=sys.stderr)
        sys.exit(1)

    # Step 2: Clone repository
    emit_log("cloning", "Cloning: repository")
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
        emit_log("patching", "Downloading: patch from S3")
        if s3_download(s3, bucket, patch_key, local_patch):
            emit_log("patching", "Applying: cumulative patch")
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
            emit_log("patching", "Thinking: cumulative patch applied successfully")
        else:
            print(
                f"WARNING: Patch not found at s3://{bucket}/{patch_key}",
                file=sys.stderr,
            )

    # Step 3: Create local branch and implement the proposal
    branch_name = (
        f"local/session-{session_id[:8]}-iter{iteration_index}-prop{proposal_index}"
    )
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_dir, check=True)
    emit_log("implementing", f"Created local branch: {branch_name}")

    screenshot_path = f"{tmp_dir}/after.png"
    emit_log("implementing", "Implementing: design proposal")
    proposal_plan_str = (
        json.dumps(proposal_plan) if isinstance(proposal_plan, dict) else proposal_plan
    )

    try:
        await implement_changes(repo_dir, proposal_plan_str)
    except Exception as e:
        emit_log("implementing", f"Implementation interrupted: {e}", detail=str(e))

    # Launch + screenshot with retry loop
    max_retries = 2  # up to 3 total attempts
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            await launch_and_screenshot(
                repo_dir,
                screenshot_path,
                device_type=device_type,
                instruction=instruction,
            )
            last_error = None
            break  # success
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                emit_log(
                    "implementing",
                    f"Dev server launch failed (attempt {attempt + 1}/{max_retries + 1}), attempting fix...",
                    detail=last_error,
                )
                await kill_dev_servers(repo_dir)
                await fix_with_claude(repo_dir, last_error, device_type=device_type)
            else:
                emit_log(
                    "implementing",
                    f"Dev server launch failed after {max_retries + 1} attempts, proceeding without screenshot",
                    detail=last_error,
                )

    if last_error:
        emit_log(
            "implementing",
            "WARNING: Could not launch dev server, screenshot may be missing",
        )

    # Step 4: Generate cumulative patch (squash everything since base_branch)
    # Parse proposal plan to get title for commit message
    try:
        _plan_data = (
            json.loads(proposal_plan)
            if isinstance(proposal_plan, str)
            else proposal_plan
        )
        commit_title = _plan_data.get("title", f"variant-{proposal_index}")
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

    # Check if there are changes to commit
    status_result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True
    )
    if not status_result.stdout.strip():
        emit_log(
            "implementing",
            "WARNING: No changes to commit. Implementation may have failed.",
        )
        # Create an empty patch and skip upload
        local_diff = f"{tmp_dir}/changes.diff"
        with open(local_diff, "w") as f:
            f.write("")
        patch_result_stdout = ""
    else:
        subprocess.run(
            ["git", "commit", "-m", f"feat: {commit_title}"],
            cwd=repo_dir,
            check=True,
        )
        # Generate format-patch (cumulative: base_branch -> HEAD)
        patch_result = subprocess.run(
            ["git", "format-patch", "-1", "HEAD", "--stdout"],
            capture_output=True,
            text=True,
            cwd=repo_dir,
            check=True,
        )
        local_diff = f"{tmp_dir}/changes.diff"
        with open(local_diff, "w") as f:
            f.write(patch_result.stdout)
        patch_result_stdout = patch_result.stdout

    # Step 5: Upload results to S3
    # Upload after screenshot
    if Path(screenshot_path).exists():
        s3_upload_file(
            s3,
            bucket,
            f"{s3_prefix}/after.png",
            screenshot_path,
            content_type="image/png",
        )

    # Upload cumulative patch (upload even if empty so downstream can detect no-changes)
    s3_upload_text(
        s3,
        bucket,
        f"{s3_prefix}/changes.diff",
        patch_result_stdout,
        content_type="text/plain",
    )

    emit_log("completed", "Implementation complete")


if __name__ == "__main__":
    asyncio.run(main())
