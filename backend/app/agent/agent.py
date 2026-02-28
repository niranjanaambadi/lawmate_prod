"""
agent/agent.py

Core LawMate agent loop.

Orchestrates Claude on AWS Bedrock with tool_use to answer
lawyer queries. Supports both streaming (SSE) and non-streaming responses.

Flow:
  1. Build system prompt from context (page + case data)
  2. Send message + conversation history to Bedrock
  3. If Claude requests a tool → dispatch to tool handler → feed result back
  4. Repeat until Claude produces a final text response
  5. Yield chunks (streaming) or return full response (non-streaming)

Usage (streaming):
    from app.agent.agent import stream_agent_response

    async for event in stream_agent_response(message, history, context, db):
        yield event  # SSE-ready dict

Usage (non-streaming):
    from app.agent.agent import run_agent

    result = await run_agent(message, history, context, db)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncGenerator

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.agent.context import AgentContext
from app.agent.prompts import get_system_prompt
from app.agent.tools.registry import dispatch_tool, get_bedrock_tools
from app.core.config import settings

logger = logging.getLogger(__name__)

BEDROCK_MODEL_ID = (settings.BEDROCK_MODEL_ID or "").strip() or "anthropic.claude-3-haiku-20240307-v1:0"
AWS_REGION       = settings.AWS_REGION

# Safety limit — prevents infinite tool-call loops
MAX_TOOL_ITERATIONS = 8
MAX_BEDROCK_RETRIES = 4


# ============================================================================
# Public: Streaming response (primary path for chat UI)
# ============================================================================

async def stream_agent_response(
    message:  str,
    history:  list[dict],
    context:  AgentContext,
    db:       Session,
) -> AsyncGenerator[dict, None]:
    """
    Streams agent response as SSE-ready event dicts.

    Yields event types:
      { "type": "tool_start",  "tool": str, "input": dict }
      { "type": "tool_end",    "tool": str, "success": bool, "summary": str }
      { "type": "text_delta",  "text": str }
      { "type": "done",        "full_text": str }
      { "type": "error",       "message": str }

    The frontend listens for these and renders accordingly:
      - tool_start → show "Searching eCourts..." spinner
      - tool_end   → show source badge
      - text_delta → stream text into chat bubble
      - done       → finalise message
    """
    try:
        messages        = _build_messages(history, message)
        system_prompt   = get_system_prompt(**context.to_prompt_context())
        bedrock_tools   = get_bedrock_tools()
        full_text       = ""
        iteration       = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            # ── Call Bedrock ──────────────────────────────────────────────
            response = await _call_bedrock(
                messages=messages,
                system_prompt=system_prompt,
                tools=bedrock_tools,
                stream=True,
            )

            current_tool_use  = None
            current_tool_input_json = ""
            stop_reason       = None

            # ── Process streaming response ────────────────────────────────
            for chunk in response:
                event_type = list(chunk.keys())[0] if chunk else None

                # Text delta
                if event_type == "contentBlockDelta":
                    delta = chunk["contentBlockDelta"].get("delta", {})

                    if "text" in delta:
                        text = delta["text"]
                        full_text += text
                        yield {"type": "text_delta", "text": text}

                    elif "toolUse" in delta:
                        # Accumulate tool input JSON (streamed in chunks)
                        current_tool_input_json += delta["toolUse"].get("input", "")

                # Tool use block start
                elif event_type == "contentBlockStart":
                    block = chunk["contentBlockStart"].get("start", {})
                    if "toolUse" in block:
                        current_tool_use = {
                            "id":   block["toolUse"]["toolUseId"],
                            "name": block["toolUse"]["name"],
                        }
                        current_tool_input_json = ""
                        yield {
                            "type": "tool_start",
                            "tool": current_tool_use["name"],
                            "input": {},
                        }

                # Tool use block end → dispatch tool
                elif event_type == "contentBlockStop":
                    if current_tool_use:
                        tool_name = current_tool_use["name"]
                        tool_id   = current_tool_use["id"]

                        # Parse accumulated input JSON
                        try:
                            tool_inputs = json.loads(current_tool_input_json) if current_tool_input_json else {}
                        except json.JSONDecodeError:
                            tool_inputs = {}

                        yield {
                            "type":  "tool_start",
                            "tool":  tool_name,
                            "input": tool_inputs,
                        }

                        # ── Dispatch tool ─────────────────────────────────
                        tool_result = await dispatch_tool(
                            tool_name=tool_name,
                            tool_inputs=tool_inputs,
                            context=context,
                        )

                        yield {
                            "type":    "tool_end",
                            "tool":    tool_name,
                            "success": tool_result.get("success", False),
                            "summary": _summarise_tool_result(tool_name, tool_result),
                        }

                        # Append assistant tool_use + tool result to messages
                        messages.append({
                            "role": "assistant",
                            "content": [{
                                "toolUse": {
                                    "toolUseId": tool_id,
                                    "name":      tool_name,
                                    "input":     tool_inputs,
                                }
                            }],
                        })
                        messages.append({
                            "role": "user",
                            "content": [{
                                "toolResult": {
                                    "toolUseId": tool_id,
                                    "content":   [{"text": json.dumps(tool_result)}],
                                    "status":    "success" if tool_result.get("success") else "error",
                                }
                            }],
                        })

                        current_tool_use        = None
                        current_tool_input_json = ""

                # Stop reason
                elif event_type == "messageStop":
                    stop_reason = chunk["messageStop"].get("stopReason")

            # ── Check stop reason ─────────────────────────────────────────
            if stop_reason == "end_turn":
                # Claude is done — append final assistant message to history
                if full_text:
                    messages.append({
                        "role":    "assistant",
                        "content": [{"text": full_text}],
                    })
                break

            elif stop_reason == "tool_use":
                # Tool was called — loop continues with updated messages
                continue

            else:
                # Unexpected stop — break safely
                logger.warning("Unexpected stop reason: %s", stop_reason)
                break

        yield {"type": "done", "full_text": full_text}

    except Exception as e:
        logger.exception("Agent stream error: %s", e)
        yield {"type": "error", "message": f"Agent error: {str(e)}"}


# ============================================================================
# Public: Non-streaming response (for background jobs / testing)
# ============================================================================

async def run_agent(
    message:  str,
    history:  list[dict],
    context:  AgentContext,
    db:       Session,
) -> dict:
    """
    Runs the agent and returns the full response as a dict.

    Returns:
        {
            "response":   str,       # Claude's final text response
            "tools_used": list[str], # tool names called during this turn
            "success":    bool,
        }
    """
    try:
        messages      = _build_messages(history, message)
        system_prompt = get_system_prompt(**context.to_prompt_context())
        bedrock_tools = get_bedrock_tools()
        full_text     = ""
        tools_used    = []
        iteration     = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            response    = await _call_bedrock(
                messages=messages,
                system_prompt=system_prompt,
                tools=bedrock_tools,
                stream=False,
            )

            stop_reason = response.get("stopReason")
            content     = response.get("output", {}).get("message", {}).get("content", [])

            # Process content blocks
            tool_results_for_next_turn = []

            for block in content:
                if "text" in block:
                    full_text += block["text"]

                elif "toolUse" in block:
                    tool_use   = block["toolUse"]
                    tool_name  = tool_use["name"]
                    tool_id    = tool_use["toolUseId"]
                    tool_inputs = tool_use.get("input", {})

                    tools_used.append(tool_name)

                    tool_result = await dispatch_tool(
                        tool_name=tool_name,
                        tool_inputs=tool_inputs,
                        context=context,
                    )

                    tool_results_for_next_turn.append({
                        "toolUseId": tool_id,
                        "result":    tool_result,
                    })

            # Append assistant message
            messages.append({
                "role":    "assistant",
                "content": content,
            })

            # If tools were called, feed results back
            if tool_results_for_next_turn:
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": tr["toolUseId"],
                                "content":   [{"text": json.dumps(tr["result"])}],
                                "status":    "success" if tr["result"].get("success") else "error",
                            }
                        }
                        for tr in tool_results_for_next_turn
                    ],
                })

            if stop_reason == "end_turn":
                break

        return {
            "response":   full_text,
            "tools_used": tools_used,
            "success":    True,
        }

    except Exception as e:
        logger.exception("Agent run error: %s", e)
        return {
            "response":   f"I encountered an error processing your request: {str(e)}",
            "tools_used": [],
            "success":    False,
        }


# ============================================================================
# Private helpers
# ============================================================================

def _build_messages(history: list[dict], new_message: str) -> list[dict]:
    """
    Builds the messages list for Bedrock from conversation history
    plus the new incoming message.

    History items are expected in format:
        { "role": "user"|"assistant", "content": str }

    Bedrock expects:
        { "role": "user"|"assistant", "content": [{"text": str}] }
    """
    messages = []

    for item in history:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = item.get("content", "")
        # Handle both string content and already-formatted content
        if isinstance(content, str):
            messages.append({
                "role":    role,
                "content": [{"text": content}],
            })
        else:
            messages.append({"role": role, "content": content})

    # Append new user message
    messages.append({
        "role":    "user",
        "content": [{"text": new_message}],
    })

    # Bedrock requires the conversation to start with a user message.
    while messages and messages[0].get("role") != "user":
        messages.pop(0)

    return messages


async def _call_bedrock(
    messages:      list[dict],
    system_prompt: str,
    tools:         list[dict],
    stream:        bool = True,
):
    """
    Makes a Bedrock converse or converse_stream call.

    Returns the stream iterator (streaming) or response dict (non-streaming).
    """
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    params = {
        "modelId":  BEDROCK_MODEL_ID,
        "system":   [{"text": system_prompt}],
        "messages": messages,
        "toolConfig": {
            "tools": [{"toolSpec": t} for t in tools],
        },
        "inferenceConfig": {
            "maxTokens":   2048,
            "temperature": 0.5,
        },
    }

    for attempt in range(1, MAX_BEDROCK_RETRIES + 1):
        try:
            if stream:
                response = client.converse_stream(**params)
                return response["stream"]
            return client.converse(**params)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code != "ThrottlingException" or attempt >= MAX_BEDROCK_RETRIES:
                raise
            sleep_s = min(8.0, 0.8 * (2 ** (attempt - 1)))
            logger.warning("Bedrock throttled (attempt %s/%s), retrying in %.1fs", attempt, MAX_BEDROCK_RETRIES, sleep_s)
            time.sleep(sleep_s)


def _summarise_tool_result(tool_name: str, result: dict) -> str:
    """
    Generates a brief human-readable summary of a tool result
    for display in the chat UI as a source badge.
    """
    if not result.get("success"):
        return f"⚠ {tool_name} failed: {result.get('error', 'Unknown error')}"

    data = result.get("data", {})

    summaries = {
        "get_case_status":          lambda d: f"Case status fetched from eCourts",
        "get_hearing_history":      lambda d: f"{d.get('count', 0)} hearings found",
        "get_cause_list":           lambda d: f"{d.get('total_listings', 0)} listings for {d.get('date', '')}",
        "get_advocate_cause_list":  lambda d: f"{d.get('total', 0)} items found — {d.get('source', '')}",
        "get_roster":               lambda d: f"Roster fetched — {d.get('count', 0)} entries",
        "search_judgments":         lambda d: f"{d.get('count', 0)} judgments from {d.get('source', '')}",
        "search_resources":         lambda d: f"{d.get('count', 0)} resources found",
        "create_calendar_event":    lambda d: d.get("message", "Event created"),
        "get_calendar_events":      lambda d: f"{d.get('count', 0)} events",
        "delete_calendar_event":    lambda d: d.get("message", "Event deleted"),
        "draft_document":           lambda d: f"Draft ready ({d.get('word_count', 0)} words)",
    }

    summariser = summaries.get(tool_name)
    if summariser and isinstance(data, dict):
        try:
            return summariser(data)
        except Exception:
            pass

    return f"✓ {tool_name} completed"
