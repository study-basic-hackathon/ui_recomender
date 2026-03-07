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
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    query,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)
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
    elif tool_name == "Bash":
        cmd = (
            params.get("command", "?")
            .replace("/workspace/repo/", "")
            .replace("/workspace/repo", ".")
        )
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


async def implement_changes(repo_dir: str, proposal_plan: str) -> None:
    """Use Claude Agent SDK to implement the design proposal."""
    prompt = f"""Implement the following UI design changes to this web application.

## Design Proposal
{proposal_plan}

## Implementation Rules

1. BEFORE editing any file, READ it first to understand its current structure and imports.
2. Make changes file by file in the order specified in the plan.
3. Preserve all existing functionality -- do not remove event handlers, routing, or data fetching unless the plan explicitly says to.
4. Match the existing code style:
   - Same indentation (tabs vs spaces)
   - Same quote style (single vs double)
   - Same component patterns (hooks vs classes, styled-components vs CSS modules vs Tailwind)
5. For CSS changes, use the same styling approach already in the project.
6. Do NOT add new npm dependencies. Work with what is already installed.
7. Do NOT leave TODO comments, placeholder text, or commented-out code.

## Verification

After all edits are complete:
1. Run the project's lint/typecheck command if one exists (check package.json scripts for "lint", "typecheck", or "check")
2. If there are errors, fix them before finishing
3. If no lint command exists, re-read each modified file to verify correctness

Complete ALL changes. Partial implementations are not acceptable.
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
                    emit_log(phase, f"Thinking: {text[:200]}", detail=block.text)
                elif isinstance(block, ToolUseBlock):
                    _emit_tool_detail(phase, block.name, json.dumps(block.input))


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
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        # Browser tools removed: server is down so browser cannot connect, wasting turns
        mcp_servers=PLAYWRIGHT_MCP_SERVERS,
        cwd=repo_dir,
        max_turns=20,
        max_budget_usd=1.5,
        include_partial_messages=True,
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(f"""The dev server failed to start. Diagnose and fix the issue.

## Error Output
```
{error_message}
```

## Diagnostic Steps (in order)

1. Check what processes are running: `ps aux | grep -E "node|vite|next|python|uvicorn"`
2. Check for port conflicts: `lsof -i :3000 -i :5173 -i :8000 2>/dev/null`
3. If a process is running but erroring, check its log output
4. Read the relevant source files mentioned in the error to identify root cause
5. Fix the code with minimal, targeted changes

## Common Fixes
- Import errors: fix the import path or add missing export
- Syntax errors: fix the syntax in the indicated file and line
- Missing dependencies: run `npm install` (do NOT add new packages)
- Port conflict: kill the conflicting process with `kill <pid>`
- Missing .env variables: create/update .env with required values
- TypeScript errors: fix type issues or add appropriate type assertions
- Backend not available: if frontend requires a backend that cannot start, mock the API calls or set API URL to empty string

## After Fixing
1. Kill any broken server processes: `pkill -f "node|vite" 2>/dev/null; sleep 1`
2. Restart the dev server: `npm run dev &`
3. Wait for it: `for i in $(seq 1 15); do curl -s http://localhost:5173 > /dev/null && break; sleep 2; done`
4. Confirm: `curl -s http://localhost:5173 | head -3`

Make only the minimum changes needed. Do NOT refactor or restructure code.
""")
        await _process_messages(client, "implementing")


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
        await client.query("""Launch the dev server for this web application.

## CRITICAL RULES
- Do NOT run `npx playwright install` -- Playwright is pre-installed.
- Do NOT install global npm packages.
- Do NOT run docker-compose -- Docker is not available in this environment.

## Steps

1. Read package.json to understand the project structure and scripts.
2. If .env.example exists, copy it to .env. Set API URLs to http://localhost:8000.
3. Run `npm install` in the project root (or frontend directory if monorepo).
4. If the project has a backend (check for /server, /backend, /api directories):
   - For Node.js: `cd <backend-dir> && npm install && npm run dev &`
   - For Python: `cd <backend-dir> && pip install -r requirements.txt && python -m uvicorn main:app --port 8000 &` (or similar)
   - If backend needs PostgreSQL/Redis/Docker, skip it and proceed with frontend only.
5. Start the frontend: `npm run dev &`
6. Poll until ready: `for i in $(seq 1 30); do curl -s http://localhost:5173 > /dev/null && break; sleep 2; done`
   (Adjust the port based on the framework: Vite=5173, Next.js=3000, CRA=3000, Angular=4200)
7. Confirm with `curl -s http://localhost:<port> | head -5`

After the server is running, state the URL (e.g., "Dev server is running at http://localhost:5173").
""")
        await _process_messages(client, "launching")

        # Phase 2: take screenshot (same session, so dev server URL is remembered)
        emit_log("screenshot", "Taking: after screenshot")
        device = "playwright_mobile" if device_type == "mobile" else "playwright"

        instruction_block = ""
        if instruction:
            instruction_block = f"""
The user requested: \"\"\"{instruction}\"\"\"
Navigate to the page most relevant to this request, not just the root URL.
If the target content is below the fold, scroll it into view before taking the screenshot.
"""

        await client.query(f"""Take a screenshot of the running application.
{instruction_block}
Steps:
1. Use mcp__{device}__browser_navigate to open the dev server URL from the previous step
2. Use mcp__{device}__browser_wait_for with text that should appear on the loaded page (e.g., a heading, nav item, or button label)
3. Use mcp__{device}__browser_snapshot to verify the page rendered correctly (not a blank page or error)
4. If the page shows a loading spinner or error, wait 5 seconds and retry the snapshot
5. If you need to scroll to the target area, use mcp__{device}__browser_evaluate with: `document.querySelector('<selector>').scrollIntoView({{behavior: 'smooth', block: 'center'}})`
6. Use mcp__{device}__browser_take_screenshot to save to {screenshot_output}

IMPORTANT: Do NOT use fullPage option. Capture only the visible viewport.
""")
        await _process_messages(client, "screenshot")

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
            proposal_plan = plan_data.get("plan", raw)
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
    try:
        await implement_changes(repo_dir, proposal_plan)
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
        capture_output=True,
        text=True,
        cwd=repo_dir,
        check=True,
    )
    local_diff = f"{tmp_dir}/changes.diff"
    with open(local_diff, "w") as f:
        f.write(patch_result.stdout)

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

    # Upload cumulative patch
    s3_upload_text(
        s3,
        bucket,
        f"{s3_prefix}/changes.diff",
        patch_result.stdout,
        content_type="text/plain",
    )

    emit_log("completed", "Implementation complete")


if __name__ == "__main__":
    asyncio.run(main())
