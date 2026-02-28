#!/usr/bin/env python3
"""PR Creation Worker: Downloads patch from S3, applies it, pushes branch, creates PR.

Session-based: This is the ONLY worker that pushes to the remote repository.
"""

import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from claude_agent_sdk import ClaudeAgentOptions, query


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


def s3_upload_text(s3, bucket, key, text):
    for attempt in range(3):
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"), ContentType="text/plain")
            print(f"Uploaded {key}")
            return
        except Exception as e:
            print(f"S3 upload attempt {attempt + 1} failed for {key}: {e}", file=sys.stderr)
            if attempt == 2:
                raise


async def push_and_create_pr(
    repo_dir: str, branch_name: str, base_branch: str, diff_summary: str
) -> str:
    """Use Claude Agent SDK to push the branch and create a PR."""
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
            cwd=repo_dir, max_turns=15, max_budget_usd=1.0,
        ),
    ):
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    collected_text.append(block.text)
                    print(f"Agent: {block.text[:200]}")

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
    print(f"=== Patch loaded ({len(diff_content)} chars) ===")

    # Step 2: Clone repository (with token auth for push)
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
    branch_name = f"feat/{ts}-ui-session-{session_id[:8]}"
    print(f"=== Creating branch: {branch_name} ===")
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_dir, check=True)

    # Step 4: Apply the patch
    print("=== Applying patch ===")
    result = subprocess.run(
        ["git", "am", "--3way", local_patch],
        cwd=repo_dir, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"git am failed: {result.stderr}", file=sys.stderr)
        print("Falling back to git apply...")
        subprocess.run(["git", "am", "--abort"], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "apply", "--3way", local_patch], cwd=repo_dir, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat: apply UI changes from session {session_id[:8]}"],
            cwd=repo_dir, check=True,
        )

    # Step 5: Unshallow for push
    subprocess.run(["git", "fetch", "--unshallow"], cwd=repo_dir, capture_output=True)

    # Step 6: Push and create PR via Agent SDK
    print("=== Creating PR via Agent SDK ===")
    diff_summary = diff_content[:10000]
    pr_url = await push_and_create_pr(repo_dir, branch_name, branch, diff_summary)

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

    print("=== PR Creation Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
