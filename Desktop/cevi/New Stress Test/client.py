"""
ElevenLabs Conversational AI Client — WebSocket Chat Mode (Fixed)
==================================================================
Uses agent_response event as the end-of-turn signal.

Protocol (from raw debug):
  - Greeting: agent_chat_response_part (start/delta/stop) → agent_response
  - User sends: user_message
  - Agent replies: agent_chat_response_part deltas → agent_tool_response(s) → agent_response
  - The agent_response event contains the COMPLETE text — use that as the signal.
"""

import time
import json
import requests
from dataclasses import dataclass, field
from typing import Optional
from config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_BASE_URL,
    TURN_TIMEOUT_SECONDS,
    MAX_TURNS_PER_CONVERSATION,
    INTER_CALL_DELAY,
)

try:
    from websockets.sync.client import connect as ws_connect
    from websockets.exceptions import ConnectionClosed
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


@dataclass
class TurnResult:
    user_message: str
    agent_response: str
    latency_ms: float
    turn_index: int
    tool_calls: list = field(default_factory=list)
    node_name: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ConversationResult:
    test_name: str
    agent_id: str
    workflow_label: str
    turns: list
    total_duration_ms: float
    passed: bool
    failure_reason: Optional[str] = None
    expected_nodes: list = field(default_factory=list)
    actual_nodes: list = field(default_factory=list)

    @property
    def avg_latency_ms(self):
        if not self.turns:
            return 0
        return sum(t.latency_ms for t in self.turns) / len(self.turns)

    @property
    def max_latency_ms(self):
        if not self.turns:
            return 0
        return max(t.latency_ms for t in self.turns)

    @property
    def p95_latency_ms(self):
        if not self.turns:
            return 0
        s = sorted(t.latency_ms for t in self.turns)
        return s[min(int(len(s) * 0.95), len(s) - 1)]

    def to_dict(self):
        return {
            "test_name": self.test_name,
            "agent_id": self.agent_id,
            "workflow_label": self.workflow_label,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "turn_count": len(self.turns),
            "passed": self.passed,
            "failure_reason": self.failure_reason,
            "expected_nodes": self.expected_nodes,
            "actual_nodes": self.actual_nodes,
            "turns": [
                {
                    "turn": t.turn_index,
                    "user": t.user_message,
                    "agent": t.agent_response[:500],
                    "latency_ms": round(t.latency_ms, 2),
                    "node": t.node_name,
                    "tool_calls": t.tool_calls,
                    "error": t.error,
                }
                for t in self.turns
            ],
        }


def _get_signed_url(agent_id: str) -> dict:
    url = f"{ELEVENLABS_BASE_URL}/convai/conversation/get-signed-url?agent_id={agent_id}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return {"success": True, "signed_url": resp.json().get("signed_url")}
        else:
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _wait_for_agent_response(ws, timeout: float = 30.0) -> tuple:
    """
    Wait for the agent_response event which contains the COMPLETE response text.

    The ElevenLabs protocol in chat mode:
      1. agent_chat_response_part (type=start)
      2. agent_chat_response_part (type=delta) x N  — streaming chunks
      3. agent_tool_response x N  — tool calls happening
      4. agent_chat_response_part (type=stop)
      5. agent_response  — FINAL complete text ← this is what we wait for

    Sometimes multiple agent_response events come (e.g. after node transitions).
    We collect ALL agent_response texts and join them.

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

        # After getting at least one agent_response, use a shorter timeout
        # to catch any follow-up responses (node transitions send multiple)
        recv_timeout = 3.0 if last_response_time and (time.perf_counter() - last_response_time > 2.0) else 10.0

        try:
            raw = ws.recv(timeout=recv_timeout)
        except TimeoutError:
            if responses:
                break  # Got response(s), silence means done
            continue  # No response yet, keep waiting
        except Exception:
            break

        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        etype = event.get("type", "")

        # Keep-alive pings
        if etype == "ping":
            pong = {"type": "pong", "event_id": event.get("ping_event", {}).get("event_id", 0)}
            ws.send(json.dumps(pong))
            continue

        # Track first text arrival for latency
        if etype == "agent_chat_response_part":
            part = event.get("text_response_part", {})
            if part.get("type") == "delta" and part.get("text") and first_text_time is None:
                first_text_time = time.perf_counter()
            continue

        # FINAL complete response — this is what we want
        if etype == "agent_response":
            text = event.get("agent_response_event", {}).get("agent_response", "")
            if text.strip():
                responses.append(text.strip())
                last_response_time = time.perf_counter()
                if first_text_time is None:
                    first_text_time = time.perf_counter()
            continue

        # Tool calls — track them
        if etype == "agent_tool_response":
            tool_info = event.get("agent_tool_response", {})
            tool_calls.append({
                "name": tool_info.get("tool_name", ""),
                "type": tool_info.get("tool_type", ""),
            })
            continue

        # Everything else — ignore
        continue

    # Combine all response texts (multiple agent_response events = node transitions)
    full_text = " ".join(responses)
    latency = ((first_text_time or time.perf_counter()) - start) * 1000
    return full_text, latency, tool_calls


def _run_ws_conversation(signed_url: str, messages: list) -> dict:
    turns = []

    try:
        ws = ws_connect(signed_url, close_timeout=5, open_timeout=15)
    except Exception as e:
        return {"success": False, "error": f"WebSocket connect failed: {e}", "turns": []}

    try:
        # Send initiation with text_only mode
        ws.send(json.dumps({
            "type": "conversation_initiation_client_data",
            "conversation_config_override": {
                "conversation": {"text_only": True}
            },
        }))

        # Collect greeting
        greeting_text, greeting_latency, greeting_tools = _wait_for_agent_response(ws, timeout=15)

        turns.append(TurnResult(
            user_message="[CONVERSATION_START]",
            agent_response=greeting_text,
            latency_ms=greeting_latency,
            turn_index=0,
            tool_calls=greeting_tools,
        ))

        # Send each user message
        for i, msg in enumerate(messages):
            if i >= MAX_TURNS_PER_CONVERSATION:
                break

            time.sleep(0.3)

            # Send user message
            ws.send(json.dumps({"type": "user_message", "text": msg}))

            # Wait for complete agent response
            agent_text, latency, tools = _wait_for_agent_response(ws, timeout=TURN_TIMEOUT_SECONDS)

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
    finally:
        try:
            ws.close()
        except Exception:
            pass

    return {"success": True, "turns": turns}


def run_conversation_test(
    agent_id: str,
    workflow_label: str,
    test_name: str,
    messages: list,
    expected_nodes: list = None,
    validators: list = None,
) -> ConversationResult:
    if not HAS_WEBSOCKETS:
        return ConversationResult(
            test_name=test_name, agent_id=agent_id, workflow_label=workflow_label,
            turns=[], total_duration_ms=0, passed=False,
            failure_reason="'websockets' not installed. Run: pip install websockets",
            expected_nodes=expected_nodes or [],
        )

    total_start = time.perf_counter()
    failure_reason = None
    actual_nodes = []

    url_result = _get_signed_url(agent_id)
    if not url_result.get("success"):
        return ConversationResult(
            test_name=test_name, agent_id=agent_id, workflow_label=workflow_label,
            turns=[], total_duration_ms=(time.perf_counter() - total_start) * 1000,
            passed=False, failure_reason=f"Signed URL failed: {url_result.get('error')}",
            expected_nodes=expected_nodes or [],
        )

    conv = _run_ws_conversation(url_result["signed_url"], messages)
    total_duration = (time.perf_counter() - total_start) * 1000
    turns = conv.get("turns", [])

    if not conv.get("success") and len(turns) < 2:
        return ConversationResult(
            test_name=test_name, agent_id=agent_id, workflow_label=workflow_label,
            turns=turns, total_duration_ms=total_duration, passed=False,
            failure_reason=f"Conversation failed: {conv.get('error')}",
            expected_nodes=expected_nodes or [],
        )

    # Run validators
    for i, turn in enumerate(turns):
        if turn.node_name:
            actual_nodes.append(turn.node_name)
        validator_idx = i - 1
        if validators and 0 <= validator_idx < len(validators) and validators[validator_idx]:
            ok, reason = validators[validator_idx](i, turn.agent_response)
            if not ok and not failure_reason:
                failure_reason = f"Turn {i} failed: {reason}"

    return ConversationResult(
        test_name=test_name, agent_id=agent_id, workflow_label=workflow_label,
        turns=turns, total_duration_ms=total_duration,
        passed=failure_reason is None, failure_reason=failure_reason,
        expected_nodes=expected_nodes or [], actual_nodes=actual_nodes,
    )


# ─── Validators ───────────────────────────────────────────────────────

def contains_text(required_phrases: list):
    def validate(turn_index, response):
        r = response.lower()
        for p in required_phrases:
            if p.lower() in r:
                return True, None
        return False, f"Missing any of: {required_phrases}"
    return validate

def contains_all(required_phrases: list):
    def validate(turn_index, response):
        r = response.lower()
        missing = [p for p in required_phrases if p.lower() not in r]
        if missing:
            return False, f"Missing: {missing}"
        return True, None
    return validate

def not_contains(forbidden_phrases: list):
    def validate(turn_index, response):
        r = response.lower()
        for p in forbidden_phrases:
            if p.lower() in r:
                return False, f"Contains forbidden: '{p}'"
        return True, None
    return validate

def response_length_between(min_chars: int, max_chars: int):
    def validate(turn_index, response):
        l = len(response)
        if l < min_chars:
            return False, f"Too short ({l} < {min_chars})"
        if l > max_chars:
            return False, f"Too long ({l} > {max_chars})"
        return True, None
    return validate
