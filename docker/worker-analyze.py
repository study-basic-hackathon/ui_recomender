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

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    query,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import StreamEvent
from prompts import LAUNCH_DEV_SERVER_PROMPT, build_screenshot_prompt, build_analyze_prompt, SYSTEM_PROMPT, READONLY_SYSTEM_PROMPT
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


def _uipro_search_path(repo_dir: str) -> str:
    return f"{repo_dir}/.claude/skills/ui-ux-pro-max/scripts/search.py"


def generate_design_context(repo_dir: str, instruction: str) -> str:
    """Run ui-ux-pro-max design system generator. Raises on failure."""
    # Initialize uipro in the cloned repo
    init_result = subprocess.run(
        ["uipro", "init", "--ai", "claude", "--force", "--offline"],
        cwd=repo_dir, capture_output=True, text=True, timeout=30,
    )
    if init_result.returncode != 0:
        raise RuntimeError(f"uipro init failed (rc={init_result.returncode}): {init_result.stderr[:500]}")

    search_py = _uipro_search_path(repo_dir)
    result = subprocess.run(
        [
            "python3", search_py,
            instruction,
            "--design-system", "-f", "markdown",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"uipro failed (rc={result.returncode}): {result.stderr[:500]}")
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("uipro returned empty output")
    return output[:8000] if len(output) > 8000 else output


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
        emit_log("screenshot", "Taking: before screenshot")
        device = "playwright_mobile" if device_type == "mobile" else "playwright"
        await client.query(build_screenshot_prompt(device, screenshot_output, instruction))
        await process_messages(client,"screenshot")


def _validate_proposals(data: dict) -> dict:
    """Validate and sanitize proposals structure."""
    proposals = data.get("proposals", [])
    valid = []
    for p in proposals:
        if isinstance(p, dict) and "title" in p and "plan" in p and "files" in p:
            valid.append(p)
    data["proposals"] = valid
    return data


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
                return _validate_proposals(data)
            if isinstance(data, list):
                return _validate_proposals(
                    {"device_type": "desktop", "proposals": data}
                )
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
                    return _validate_proposals(data)
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
                    return _validate_proposals(data)
            except json.JSONDecodeError:
                pass

    # Strategy 3: Extract from markdown code blocks in full text
    for pattern in [r"```json\s*(.*?)```", r"```\s*(.*?)```"]:
        m = re.search(pattern, full_text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1).strip())
                if isinstance(data, dict) and "proposals" in data:
                    return _validate_proposals(data)
                if isinstance(data, list):
                    return _validate_proposals(
                        {"device_type": "desktop", "proposals": data}
                    )
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
    emit_log("analyzing", "Thinking: Generating design system recommendations")
    try:
        design_context = generate_design_context(repo_dir, instruction)
        emit_log("analyzing", "Thinking: Design system context generated successfully")
    except Exception as e:
        emit_log(
            "analyzing",
            "Warning: Failed to generate design system context; continuing without it",
            detail=str(e),
        )
        design_context = ""

    prompt = build_analyze_prompt(instruction, num_proposals, design_context=design_context)

    collected_text = []

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Read", "Glob", "Grep"],
            cwd=repo_dir,
            max_turns=20,
            max_budget_usd=float(os.environ.get("ANALYZE_MAX_BUDGET_USD", "1.5")),
            include_partial_messages=True,
            thinking={"type": "adaptive"},
        ),
    ):
        if isinstance(msg, StreamEvent):
            continue  # Skip streaming events; logs emitted from AssistantMessage only

        # Collect text content from assistant messages
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text = block.text.strip()
                    if text.startswith("Browser") or text.startswith("Searching"):
                        continue
                    emit_log("analyzing", f"Thinking: {text[:200]}", detail=block.text)
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
    emit_log("cloning", "Cloning: repository")
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

    # Step 2: Code analysis + device detection + proposal generation (no browser needed)
    emit_log("analyzing", "Thinking: Generating design proposals")
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
    emit_log(
        "analyzing",
        f"Thinking: Generated {len(proposals)} proposals (device: {device_type})",
    )

    # Step 3: Launch dev server + take before screenshot (with determined device_type)
    before_path = f"{tmp_dir}/before.png"
    try:
        await launch_and_screenshot(
            repo_dir, before_path, device_type=device_type, instruction=instruction
        )
    except Exception as e:
        emit_log("screenshot", f"Screenshot failed, continuing without it: {e}")

    # Step 4: Upload results to S3
    # Upload before screenshot
    if Path(before_path).exists():
        s3_upload_file(
            s3,
            bucket,
            f"{s3_prefix}/before.png",
            before_path,
            content_type="image/png",
        )

    # Upload proposals.json (includes device_type)
    proposals_data = {
        "device_type": device_type,
        "instruction": instruction,
        "proposals": proposals,
    }
    s3_upload_text(
        s3,
        bucket,
        f"{s3_prefix}/proposals.json",
        json.dumps(proposals_data, ensure_ascii=False, indent=2),
        content_type="application/json",
    )

    emit_log("completed", "Analysis complete")


if __name__ == "__main__":
    asyncio.run(main())
