#!/usr/bin/env python3
"""Implementation Worker: Clones repo, implements a design proposal via Claude Agent SDK, takes after screenshot."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query


def generate_branch_name(proposal_index: int | str) -> str:
    """Generate a unique branch name like feat/20260217-143052-claude_idea-1."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"feat/{ts}-claude_idea-{proposal_index}"


def create_branch(repo_dir: str, branch_name: str) -> None:
    """Create and checkout a new branch."""
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=repo_dir,
        check=True,
    )
    print(f"Created branch: {branch_name}")


async def implement_proposal(
    repo_dir: str, proposal_plan: str, screenshot_output: str
) -> None:
    """Use Claude Agent SDK to implement the design proposal, start dev server, and take screenshot."""
    prompt = f"""You are implementing UI changes to a web application located at {repo_dir}.

Here is the specific design proposal to implement:

{proposal_plan}

Follow these steps in order:

## Step 1: Implement the changes
- Implement all the changes described in the plan
- All file modifications must be correct and complete
- Follow existing code conventions and patterns
- Do not leave any TODO comments or incomplete implementations

## Step 2: Start the dev server and take a screenshot
After implementing the changes:
1. Investigate how to start the dev server for this project (check package.json scripts, README, etc.)
2. Install dependencies if needed
3. Start the dev server in the background using Bash (e.g. `npm run dev &` or whatever is appropriate)
4. Wait for the server to become ready (poll with curl until it responds)
5. Once the server is ready, take a screenshot by running:
   `node /usr/local/bin/take-screenshot.mjs <server_url> {screenshot_output}`
   where <server_url> is the URL the dev server is listening on (e.g. http://localhost:5173)
6. Make sure the screenshot file was created at {screenshot_output}

IMPORTANT: The screenshot is critical. Do your best to get the dev server running and take the screenshot.
"""

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=40,
            max_budget_usd=3.0,
        ),
    ):
        # Log progress messages
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    print(f"Agent: {block.text[:200]}")


async def main() -> None:
    # Read environment variables
    job_id = os.environ["JOB_ID"]
    repo_url = os.environ["REPO_URL"]
    branch = os.environ.get("BRANCH", "main")
    proposal_index = os.environ["PROPOSAL_INDEX"]
    artifact_dir = f"/artifacts/{job_id}/proposals/{proposal_index}"
    repo_dir = "/workspace/repo"
    os.makedirs(artifact_dir, exist_ok=True)

    # Read proposal plan from file (avoids K8s env var size limits)
    plan_file = f"/artifacts/{job_id}/proposal_{proposal_index}_plan.txt"
    if Path(plan_file).exists():
        proposal_plan = Path(plan_file).read_text()
    else:
        proposal_plan = os.environ.get("PROPOSAL_PLAN", "")

    if not proposal_plan:
        print("Error: No proposal plan provided", file=sys.stderr)
        sys.exit(1)

    # Step 1: Clone repository
    print("=== Cloning repository ===")
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, repo_dir],
        check=True,
    )

    # Step 2: Create feature branch
    branch_name = generate_branch_name(proposal_index)
    print(f"=== Creating branch: {branch_name} ===")
    create_branch(repo_dir, branch_name)

    # Step 3: Implement the proposal + take screenshot via Claude Agent SDK
    screenshot_path = f"{artifact_dir}/after.png"
    print("=== Implementing design proposal ===")
    await implement_proposal(repo_dir, proposal_plan, screenshot_path)

    # Step 4: Save the diff
    print("=== Saving changes diff ===")
    os.chdir(repo_dir)
    diff_result = subprocess.run(
        ["git", "diff"],
        capture_output=True,
        text=True,
    )
    with open(f"{artifact_dir}/changes.diff", "w") as f:
        f.write(diff_result.stdout)

    # Output artifacts to stdout with markers so Backend can extract from pod logs
    import base64

    diff_file = Path(f"{artifact_dir}/changes.diff")
    if diff_file.exists():
        print("===ARTIFACT:changes.diff:START===")
        print(diff_file.read_text())
        print("===ARTIFACT:changes.diff:END===")

    after_path = Path(f"{artifact_dir}/after.png")
    if after_path.exists():
        b64 = base64.b64encode(after_path.read_bytes()).decode()
        print("===ARTIFACT:after.png:START===")
        print(b64)
        print("===ARTIFACT:after.png:END===")

    print("=== Implementation Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
