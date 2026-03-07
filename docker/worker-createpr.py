#!/usr/bin/env python3
"""PR Creation Worker: Downloads patch from S3, applies it, pushes branch, creates PR.

Session-based: This is the ONLY worker that pushes to the remote repository.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query, AssistantMessage, TextBlock
from prompts import build_pr_prompt, SYSTEM_PROMPT
from worker_common import get_s3_client, s3_download, s3_upload_text


async def push_and_create_pr(
    repo_dir: str,
    branch_name: str,
    base_branch: str,
    diff_summary: str,
    plan_context: str = "",
) -> str:
    """Use Claude Agent SDK to push the branch and create a PR."""
    prompt = build_pr_prompt(branch_name, base_branch, diff_summary, plan_context)
    collected_text: list[str] = []

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Bash"],
            cwd=repo_dir,
            max_turns=15,
            max_budget_usd=1.0,
        ),
    ):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    collected_text.append(block.text)

    full_text = "\n".join(collected_text)
    for line in full_text.split("\n"):
        if "PR_URL:" in line:
            return line.split("PR_URL:")[-1].strip()

    urls = re.findall(r"https://github\.com/[^\s)\"']+/pull/\d+", full_text)
    if urls:
        return urls[0]
    return ""


async def main() -> None:
    session_id = os.environ["SESSION_ID"]
    iteration_index = int(os.environ["ITERATION_INDEX"])
    repo_url = os.environ["REPO_URL"]
    branch = os.environ.get("BRANCH", "main")
    proposal_index = os.environ["PROPOSAL_INDEX"]
    github_token = os.environ["GITHUB_TOKEN"]

    bucket = os.environ["S3_BUCKET"]
    s3 = get_s3_client()
    tmp_dir = "/tmp/artifacts"
    os.makedirs(tmp_dir, exist_ok=True)

    os.environ["GH_TOKEN"] = github_token

    # Step 1: Download patch from S3
    patch_key = (
        f"sessions/{session_id}/iterations/{iteration_index}"
        f"/proposals/{proposal_index}/changes.diff"
    )
    local_patch = f"{tmp_dir}/changes.diff"
    if not s3_download(s3, bucket, patch_key, local_patch):
        print(f"Error: Patch not found at s3://{bucket}/{patch_key}", file=sys.stderr)
        sys.exit(1)
    diff_content = Path(local_patch).read_text()
    if not diff_content.strip():
        print("Patch is empty, no changes to push. Skipping PR creation.")
        sys.exit(0)

    # Step 1.5: Download plan.json for proposal context
    plan_key = (
        f"sessions/{session_id}/iterations/{iteration_index}"
        f"/proposals/{proposal_index}/plan.json"
    )
    local_plan = f"{tmp_dir}/plan.json"
    plan_context = ""
    if s3_download(s3, bucket, plan_key, local_plan):
        try:
            plan_data = json.loads(Path(local_plan).read_text())
            plan_context = f"""
## Proposal Context
User Request: {plan_data.get('instruction', 'N/A')}
Title: {plan_data.get('title', 'N/A')}
Concept: {plan_data.get('concept', 'N/A')}
"""
        except (json.JSONDecodeError, KeyError):
            pass

    # Step 2: Clone repository (with token auth for push)
    repo_dir = "/workspace/repo"
    if repo_url.startswith("https://github.com/"):
        auth_repo_url = repo_url.replace(
            "https://github.com/",
            f"https://x-access-token:{github_token}@github.com/",
        )
    else:
        auth_repo_url = repo_url

    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, auth_repo_url, repo_dir],
        check=True,
    )

    # Step 3: Create a new branch
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"feat/{ts}-ui-session-{session_id[:8]}"
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_dir, check=True)

    # Step 4: Apply the patch
    result = subprocess.run(
        ["git", "am", "--3way", local_patch],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"git am failed: {result.stderr}", file=sys.stderr)
        print("Falling back to git apply...")
        subprocess.run(["git", "am", "--abort"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "apply", "--3way", local_patch], cwd=repo_dir, check=True
        )
        subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"feat: apply UI changes from session {session_id[:8]}",
            ],
            cwd=repo_dir,
            check=True,
        )

    # Step 5: Unshallow for push
    subprocess.run(["git", "fetch", "--unshallow"], cwd=repo_dir, capture_output=True)

    # Step 6: Push and create PR via Agent SDK
    # Truncate diff at line boundaries to avoid cutting mid-hunk
    diff_lines = diff_content.splitlines()
    summary_lines = []
    char_count = 0
    truncated = False
    for line in diff_lines:
        if char_count + len(line) > 10000:
            truncated = True
            break
        summary_lines.append(line)
        char_count += len(line) + 1
    diff_summary = "\n".join(summary_lines)
    if truncated:
        diff_summary += "\n\n... (diff truncated, showing first ~10000 chars)"
    pr_url = await push_and_create_pr(
        repo_dir, branch_name, branch, diff_summary, plan_context=plan_context
    )

    if pr_url:
        print(f"PR created: {pr_url}")
        pr_url_key = (
            f"sessions/{session_id}/iterations/{iteration_index}"
            f"/proposals/{proposal_index}/pr_url.txt"
        )
        s3_upload_text(s3, bucket, pr_url_key, pr_url)
    else:
        print("Error: Failed to extract PR URL from agent output", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
