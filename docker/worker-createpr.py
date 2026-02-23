#!/usr/bin/env python3
"""PR Creation Worker: Applies a diff and creates a PR using Claude Agent SDK for quality descriptions."""

import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query


async def push_and_create_pr(
    repo_dir: str, branch_name: str, base_branch: str, diff_summary: str
) -> str:
    """Use Claude Agent SDK to push the branch and create a PR with a good description."""
    prompt = f"""You are creating a GitHub Pull Request for UI design changes.

The repository is at {repo_dir}. You are on branch "{branch_name}".
The base branch is "{base_branch}".

Here is a summary of the changes that were applied (from the diff):

```diff
{diff_summary}
```

Please do the following:

1. Read the changed files to understand the full context of the changes.
2. Push the current branch to the remote:
   `git push origin {branch_name}`
3. Create a GitHub PR using the `gh` CLI:
   `gh pr create --base {base_branch} --head {branch_name} --title "<concise title>" --body "<detailed description>"`

   The PR title should be concise and descriptive (under 70 chars).
   The PR description should include:
   - A clear summary of what UI changes were made and why
   - A list of the key files changed
   - Any visual/behavioral changes the reviewer should look for

4. After creating the PR, output the PR URL on a line by itself prefixed with "PR_URL:" like:
   PR_URL: https://github.com/...

IMPORTANT: You MUST output the PR URL in that exact format so it can be extracted.
"""

    collected_text: list[str] = []
    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Bash", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=15,
            max_budget_usd=1.0,
        ),
    ):
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    collected_text.append(block.text)
                    print(f"Agent: {block.text[:200]}")

    full_text = "\n".join(collected_text)

    # Extract PR URL from agent output
    for line in full_text.split("\n"):
        if "PR_URL:" in line:
            return line.split("PR_URL:")[-1].strip()

    # Fallback: find a github.com PR URL in the output
    urls = re.findall(r"https://github\.com/[^\s)\"']+/pull/\d+", full_text)
    if urls:
        return urls[0]

    return ""


async def main() -> None:
    job_id = os.environ["JOB_ID"]
    repo_url = os.environ["REPO_URL"]
    branch = os.environ.get("BRANCH", "main")
    proposal_index = os.environ["PROPOSAL_INDEX"]
    github_token = os.environ["GITHUB_TOKEN"]

    artifact_dir = f"/artifacts/{job_id}/proposals/{proposal_index}"

    # Configure gh CLI authentication
    os.environ["GH_TOKEN"] = github_token

    # Step 1: Read the diff
    diff_path = f"{artifact_dir}/changes.diff"
    if not Path(diff_path).exists():
        print(f"Error: Diff not found at {diff_path}", file=sys.stderr)
        sys.exit(1)
    diff_content = Path(diff_path).read_text()
    print(f"=== Diff loaded ({len(diff_content)} chars) ===")

    # Step 2: Clone repository (shallow, with token auth for push)
    print("=== Cloning repository ===")
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
    branch_name = f"feat/{ts}-ui-proposal-{proposal_index}"
    print(f"=== Creating branch: {branch_name} ===")
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=repo_dir,
        check=True,
    )

    # Step 4: Apply the diff using git am (format-patch output)
    print("=== Applying diff ===")
    result = subprocess.run(
        ["git", "am", "--3way", diff_path],
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
            ["git", "apply", "--3way", diff_path],
            cwd=repo_dir,
            check=True,
        )
        subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat: apply UI proposal {proposal_index}"],
            cwd=repo_dir,
            check=True,
        )

    # Step 5: Unshallow for push compatibility
    subprocess.run(
        ["git", "fetch", "--unshallow"],
        cwd=repo_dir,
        capture_output=True,
    )

    # Step 6: Use Agent SDK to push and create PR with good description
    print("=== Creating PR via Agent SDK ===")
    # Provide first 10000 chars of diff for context
    diff_summary = diff_content[:10000]
    pr_url = await push_and_create_pr(repo_dir, branch_name, branch, diff_summary)

    if pr_url:
        print(f"PR created: {pr_url}")
        pr_url_file = f"{artifact_dir}/pr_url.txt"
        Path(pr_url_file).write_text(pr_url)

        print("===ARTIFACT:pr_url.txt:START===")
        print(pr_url)
        print("===ARTIFACT:pr_url.txt:END===")
    else:
        print("Error: Failed to extract PR URL from agent output", file=sys.stderr)
        sys.exit(1)

    print("=== PR Creation Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
