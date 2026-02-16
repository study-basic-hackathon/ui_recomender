#!/usr/bin/env python3
"""Analyzer Worker: Clones repo, takes before screenshot, generates design proposals via Claude Agent SDK."""

import asyncio
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query


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


async def generate_proposals(
    repo_dir: str, instruction: str, num_proposals: int
) -> list[dict]:
    """Use Claude Agent SDK to analyze the repo and generate design proposals."""
    prompt = f"""You are a UI/UX design expert analyzing a web application repository.
The user wants the following UI changes:

{instruction}

Analyze the codebase thoroughly and generate exactly {num_proposals} different design proposals.
Each proposal should take a meaningfully different approach.

You MUST output ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
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
"""

    collected_text = []
    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=10,
        ),
    ):
        # Collect text content from assistant messages
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    collected_text.append(block.text)

    full_text = "\n".join(collected_text)

    # Parse JSON from the response (handle potential markdown wrapping)
    json_text = full_text
    if "```json" in json_text:
        json_text = json_text.split("```json")[1].split("```")[0]
    elif "```" in json_text:
        json_text = json_text.split("```")[1].split("```")[0]

    try:
        data = json.loads(json_text.strip())
        if "proposals" in data:
            return data["proposals"]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError as e:
        print(f"Failed to parse proposals JSON: {e}", file=sys.stderr)
        print(f"Raw text: {full_text[:1000]}", file=sys.stderr)

    return []


async def main() -> None:
    # Read environment variables
    job_id = os.environ["JOB_ID"]
    repo_url = os.environ["REPO_URL"]
    branch = os.environ.get("BRANCH", "main")
    instruction = os.environ["INSTRUCTION"]
    num_proposals = int(os.environ.get("NUM_PROPOSALS", "3"))

    artifact_dir = f"/artifacts/{job_id}"
    repo_dir = "/workspace/repo"
    os.makedirs(artifact_dir, exist_ok=True)

    # Step 1: Clone repository
    print("=== Cloning repository ===")
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, repo_dir],
        check=True,
    )

    # Step 2: Take before screenshot via Agent SDK
    print("=== Taking before screenshot ===")
    await take_before_screenshot(repo_dir, f"{artifact_dir}/before.png")

    # Step 3: Generate design proposals via Claude Agent SDK
    print("=== Generating design proposals ===")
    proposals = await generate_proposals(repo_dir, instruction, num_proposals)

    # Step 4: Save results to file and output to stdout for Backend retrieval
    print(f"=== Generated {len(proposals)} proposals ===")
    result = {"proposals": proposals}
    with open(f"{artifact_dir}/proposals.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Output artifacts to stdout with markers so Backend can extract from pod logs

    proposals_json = json.dumps(result, ensure_ascii=False)
    print(f"===ARTIFACT:proposals.json:START===")
    print(proposals_json)
    print(f"===ARTIFACT:proposals.json:END===")

    before_path = Path(f"{artifact_dir}/before.png")
    if before_path.exists():
        b64 = base64.b64encode(before_path.read_bytes()).decode()
        print(f"===ARTIFACT:before.png:START===")
        print(b64)
        print(f"===ARTIFACT:before.png:END===")

    print(f"=== Analysis Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
