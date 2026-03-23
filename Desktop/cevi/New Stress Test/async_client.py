"""
Async ElevenLabs Conversational AI Client
==========================================
Async version of client.py for parallel conversation execution.
Uses websockets async API + aiohttp for HTTP calls.

Reuses TurnResult and ConversationResult from client.py.
"""

import asyncio
import json
import time
import aiohttp
from typing import Optional
from websockets import connect as ws_async_connect
from websockets.exceptions import ConnectionClosed

from client import TurnResult, ConversationResult
from config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_BASE_URL,
    TURN_TIMEOUT_SECONDS,
    MAX_TURNS_PER_CONVERSATION,
)


async def async_get_signed_url(
    agent_id: str,
    session: aiohttp.ClientSession,
    api_key: str = ELEVENLABS_API_KEY,
    base_url: str = ELEVENLABS_BASE_URL,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> dict:
    """Get signed WebSocket URL with exponential backoff for rate limits."""
    url = f"{base_url}/convai/conversation/get-signed-url?agent_id={agent_id}"
    headers = {"xi-api-key": api_key}

    for attempt in range(max_retries + 1):
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"success": True, "signed_url": data.get("signed_url")}
                elif resp.status == 429:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    text = await resp.text()
                    return {"success": False, "error": f"HTTP {resp.status}: {text[:300]}"}
        except asyncio.TimeoutError:
            if attempt < max_retries:
                await asyncio.sleep(base_delay * (attempt + 1))
                continue
            return {"success": False, "error": "Timeout getting signed URL"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "Exhausted retries for signed URL"}


async def async_wait_for_agent_response(
    ws,
    timeout: float = 30.0,
) -> tuple:
    """
    Async version of _wait_for_agent_response.
    Returns: (full_text, latency_ms, tool_calls_list)
    """
    start = time.perf_counter()
    first_text_time = None
    responses = []
    tool_calls = []
    last_response_time = None

    while True:
        elapsed = time.perf_counter() - start
        if elapsed > timeout:
            break

        recv_timeout = 3.0 if (
            last_response_time
            and (time.perf_counter() - last_response_time > 2.0)
        ) else 10.0

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
        except asyncio.TimeoutError:
            if responses:
                break
            continue
        except ConnectionClosed:
            break
        except Exception:
            break

        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        etype = event.get("type", "")

        if etype == "ping":
            pong = {
                "type": "pong",
                "event_id": event.get("ping_event", {}).get("event_id", 0),
            }
            await ws.send(json.dumps(pong))
            continue

        if etype == "agent_chat_response_part":
            part = event.get("text_response_part", {})
            if (
                part.get("type") == "delta"
                and part.get("text")
                and first_text_time is None
            ):
                first_text_time = time.perf_counter()
            continue

        if etype == "agent_response":
            text = event.get("agent_response_event", {}).get("agent_response", "")
            if text.strip():
                responses.append(text.strip())
                last_response_time = time.perf_counter()
                if first_text_time is None:
                    first_text_time = time.perf_counter()
            continue

        if etype == "agent_tool_response":
            tool_info = event.get("agent_tool_response", {})
            tool_calls.append({
                "name": tool_info.get("tool_name", ""),
                "type": tool_info.get("tool_type", ""),
            })
            continue

    full_text = " ".join(responses)
    latency = ((first_text_time or time.perf_counter()) - start) * 1000
    return full_text, latency, tool_calls


async def async_run_ws_conversation(
    signed_url: str,
    messages: list,
    turn_timeout: float = TURN_TIMEOUT_SECONDS,
    max_turns: int = MAX_TURNS_PER_CONVERSATION,
) -> dict:
    """Async conversation with pre-written messages."""
    turns = []

    try:
        async with ws_async_connect(
            signed_url, close_timeout=5, open_timeout=15,
        ) as ws:
            await ws.send(json.dumps({
                "type": "conversation_initiation_client_data",
                "conversation_config_override": {
                    "conversation": {"text_only": True}
                },
            }))

            greeting_text, greeting_latency, greeting_tools = (
                await async_wait_for_agent_response(ws, timeout=15)
            )

            turns.append(TurnResult(
                user_message="[CONVERSATION_START]",
                agent_response=greeting_text,
                latency_ms=greeting_latency,
                turn_index=0,
                tool_calls=greeting_tools,
            ))

            for i, msg in enumerate(messages):
                if i >= max_turns:
                    break
                await asyncio.sleep(0.3)
                await ws.send(json.dumps({"type": "user_message", "text": msg}))
                agent_text, latency, tools = await async_wait_for_agent_response(
                    ws, timeout=turn_timeout,
                )

                turn = TurnResult(
                    user_message=msg,
                    agent_response=agent_text,
                    latency_ms=latency,
                    turn_index=i + 1,
                    tool_calls=tools,
                )
                turns.append(turn)

                if not agent_text:
                    turn.error = "Empty response (timeout or connection closed)"
                    break

    except ConnectionClosed as e:
        return {"success": len(turns) > 1, "error": f"Connection closed: {e}", "turns": turns}
    except Exception as e:
        return {"success": False, "error": str(e), "turns": turns}

    return {"success": True, "turns": turns}


async def async_run_adaptive_conversation(
    signed_url: str,
    persona: 'CallerPersona',
    turn_timeout: float = TURN_TIMEOUT_SECONDS,
    max_turns: int = 15,
) -> dict:
    """
    Async adaptive conversation — WebSocket + LLM caller agent.
    Uses asyncio.to_thread for the blocking Anthropic API call.
    """
    from caller_agent import generate_caller_response

    turns = []
    conversation_history = []

    try:
        async with ws_async_connect(
            signed_url, close_timeout=5, open_timeout=15,
        ) as ws:
            await ws.send(json.dumps({
                "type": "conversation_initiation_client_data",
                "conversation_config_override": {
                    "conversation": {"text_only": True}
                },
            }))

            greeting_text, greeting_latency, greeting_tools = (
                await async_wait_for_agent_response(ws, timeout=15)
            )

            turns.append(TurnResult(
                user_message="[CONVERSATION_START]",
                agent_response=greeting_text,
                latency_ms=greeting_latency,
                turn_index=0,
                tool_calls=greeting_tools,
            ))

            conversation_history.append({"role": "agent", "text": greeting_text})

            for i in range(max_turns):
                caller_resp = await asyncio.to_thread(
                    generate_caller_response,
                    persona,
                    conversation_history,
                    i,
                )

                conversation_history.append({"role": "caller", "text": caller_resp.message})

                await ws.send(json.dumps({
                    "type": "user_message",
                    "text": caller_resp.message,
                }))

                agent_text, latency, tools = await async_wait_for_agent_response(
                    ws, timeout=turn_timeout,
                )

                turns.append(TurnResult(
                    user_message=caller_resp.message,
                    agent_response=agent_text,
                    latency_ms=latency,
                    turn_index=i + 1,
                    tool_calls=tools,
                ))

                conversation_history.append({"role": "agent", "text": agent_text})

                if not agent_text:
                    break
                if caller_resp.should_end_call:
                    break

    except ConnectionClosed as e:
        return {"success": len(turns) > 1, "error": f"Connection closed: {e}", "turns": turns}
    except Exception as e:
        return {"success": False, "error": str(e), "turns": turns}

    return {"success": True, "turns": turns}


async def async_run_conversation_test(
    agent_id: str,
    workflow_label: str,
    test_name: str,
    session: aiohttp.ClientSession,
    messages: list = None,
    persona: 'CallerPersona' = None,
    expected_nodes: list = None,
    semaphore: asyncio.Semaphore = None,
) -> ConversationResult:
    """
    Async version of run_conversation_test.
    Supports both scripted (messages) and adaptive (persona) modes.
    """

    async def _inner():
        total_start = time.perf_counter()

        url_result = await async_get_signed_url(agent_id, session)
        if not url_result.get("success"):
            return ConversationResult(
                test_name=test_name,
                agent_id=agent_id,
                workflow_label=workflow_label,
                turns=[],
                total_duration_ms=(time.perf_counter() - total_start) * 1000,
                passed=False,
                failure_reason=f"Signed URL failed: {url_result.get('error')}",
                expected_nodes=expected_nodes or [],
            )

        signed_url = url_result["signed_url"]

        if persona is not None:
            conv = await async_run_adaptive_conversation(
                signed_url, persona,
            )
        else:
            conv = await async_run_ws_conversation(
                signed_url, messages or [],
            )

        total_duration = (time.perf_counter() - total_start) * 1000
        turns = conv.get("turns", [])
        failure_reason = None

        if not conv.get("success") and len(turns) < 2:
            failure_reason = f"Conversation failed: {conv.get('error')}"

        return ConversationResult(
            test_name=test_name,
            agent_id=agent_id,
            workflow_label=workflow_label,
            turns=turns,
            total_duration_ms=total_duration,
            passed=failure_reason is None,
            failure_reason=failure_reason,
            expected_nodes=expected_nodes or [],
        )

    if semaphore:
        async with semaphore:
            return await _inner()
    return await _inner()
