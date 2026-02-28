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

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Bash", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=20,
            max_budget_usd=1.0,
        ),
    ):
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    print(f"Screenshot Agent: {block.text[:200]}")


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
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "proposals" in data:
                return data["proposals"]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue

    # Strategy 2: Search for {"proposals": ...} in the concatenated text using regex
    full_text = "\n".join(collected_text)
    match = re.search(r'\{"proposals"\s*:\s*\[.*\]\s*\}', full_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if "proposals" in data:
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
    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=30,
        ),
    ):
        # Collect text content from assistant messages
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    collected_text.append(block.text)

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
    print("=== Cloning repository ===")
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
        print(f"=== Downloading patch from S3: {patch_key} ===")
        if s3_download(s3, bucket, patch_key, local_patch):
            print("=== Applying cumulative patch ===")
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
            print("=== Cumulative patch applied successfully ===")
        else:
            print(
                f"WARNING: Patch not found at s3://{bucket}/{patch_key}",
                file=sys.stderr,
            )

    # Step 2: Take before screenshot
    print("=== Taking before screenshot ===")
    before_path = f"{tmp_dir}/before.png"
    await take_before_screenshot(repo_dir, before_path)

    # Step 3: Generate design proposals via Claude Agent SDK
    print("=== Generating design proposals ===")
    proposals = await generate_proposals(repo_dir, instruction, num_proposals)
    print(f"=== Generated {len(proposals)} proposals ===")

    # Step 4: Upload results to S3
    print("=== Uploading results to S3 ===")

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

    print("=== Analysis Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
