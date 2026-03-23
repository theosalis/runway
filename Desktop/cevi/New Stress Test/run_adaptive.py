#!/usr/bin/env python3
"""
Adaptive Conversation Runner — LLM-Powered Caller
====================================================
Uses Claude Haiku to generate contextually-appropriate caller responses
in real-time based on what the ElevenLabs agent actually says.

Usage:
  export ELEVENLABS_API_KEY=your_key
  export WORKFLOW_1_AGENT_ID=your_agent_id
  export ANTHROPIC_API_KEY=your_key

  python3 run_adaptive.py                    # All 120 tests
  python3 run_adaptive.py --first 5          # First 5 tests
  python3 run_adaptive.py --category A       # Only category A
  python3 run_adaptive.py --test A01         # Single test by prefix
  python3 run_adaptive.py --dry-run          # Print plan
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from collections import Counter

from config import WORKFLOW_1_AGENT_ID, RESULTS_DIR, ADAPTIVE_MAX_TURNS
from client import TurnResult, ConversationResult, _get_signed_url
from caller_agent import (
    CallerPersona, generate_caller_response, scenario_to_persona,
    ANTHROPIC_API_KEY,
)
from test_12_ehr_integration import ALL_SCENARIOS
from llm_judge import SEVERITY_LABELS

try:
    from websockets.sync.client import connect as ws_connect
    from websockets.exceptions import ConnectionClosed
except ImportError:
    print("ERROR: pip install websockets")
    sys.exit(1)


def _wait_for_agent_response(ws, timeout=30.0):
    """Reuse the protocol logic from client.py."""
    from client import _wait_for_agent_response as _wait
    return _wait(ws, timeout)


def run_adaptive_conversation(
    agent_id: str,
    workflow_label: str,
    test_name: str,
    persona: CallerPersona,
) -> ConversationResult:
    """Run a single adaptive conversation using sync WebSocket."""
    total_start = time.perf_counter()
    turns = []
    conversation_history = []

    print(f"  [1] Getting signed URL...", flush=True)
    url_result = _get_signed_url(agent_id)
    if not url_result.get("success"):
        print(f"  [!] Signed URL FAILED: {url_result.get('error')}")
        return ConversationResult(
            test_name=test_name, agent_id=agent_id, workflow_label=workflow_label,
            turns=[], total_duration_ms=(time.perf_counter() - total_start) * 1000,
            passed=False, failure_reason=f"Signed URL failed: {url_result.get('error')}",
        )
    print(f"  [2] Connecting WebSocket...", flush=True)

    try:
        ws = ws_connect(url_result["signed_url"], close_timeout=5, open_timeout=15)
    except Exception as e:
        print(f"  [!] WebSocket connect FAILED: {e}")
        return ConversationResult(
            test_name=test_name, agent_id=agent_id, workflow_label=workflow_label,
            turns=[], total_duration_ms=(time.perf_counter() - total_start) * 1000,
            passed=False, failure_reason=f"WebSocket connect failed: {e}",
        )

    try:
        print(f"  [3] Sending initiation...", flush=True)
        ws.send(json.dumps({
            "type": "conversation_initiation_client_data",
            "conversation_config_override": {
                "conversation": {"text_only": True}
            },
        }))

        print(f"  [4] Waiting for greeting (15s timeout)...", flush=True)
        greeting_text, greeting_latency, greeting_tools = _wait_for_agent_response(ws, timeout=15)

        turns.append(TurnResult(
            user_message="[CONVERSATION_START]",
            agent_response=greeting_text,
            latency_ms=greeting_latency,
            turn_index=0,
            tool_calls=greeting_tools,
        ))
        conversation_history.append({"role": "agent", "text": greeting_text})
        print(f"  [5] Greeting received: {greeting_text[:80]}...", flush=True)

        max_turns = persona.max_turns or ADAPTIVE_MAX_TURNS

        for i in range(max_turns):
            print(f"  [turn {i+1}] Generating caller response...", flush=True)
            caller_resp = generate_caller_response(persona, conversation_history, i)
            conversation_history.append({"role": "caller", "text": caller_resp.message})
            print(f"  [turn {i+1}] Caller: {caller_resp.message[:80]}", flush=True)

            time.sleep(0.3)
            ws.send(json.dumps({"type": "user_message", "text": caller_resp.message}))

            print(f"  [turn {i+1}] Waiting for agent (30s timeout)...", flush=True)
            agent_text, latency, tools = _wait_for_agent_response(ws, timeout=30)

            turns.append(TurnResult(
                user_message=caller_resp.message,
                agent_response=agent_text,
                latency_ms=latency,
                turn_index=i + 1,
                tool_calls=tools,
            ))
            conversation_history.append({"role": "agent", "text": agent_text})
            print(f"  [turn {i+1}] Agent: {agent_text[:80] if agent_text else '(empty)'}", flush=True)

            if not agent_text:
                print(f"  [turn {i+1}] Agent gave empty response, ending.", flush=True)
                break
            if caller_resp.should_end_call:
                print(f"  [turn {i+1}] Caller signaled end of call.", flush=True)
                break

    except ConnectionClosed as e:
        pass
    except Exception as e:
        pass
    finally:
        try:
            ws.close()
        except Exception:
            pass

    total_duration = (time.perf_counter() - total_start) * 1000
    return ConversationResult(
        test_name=test_name,
        agent_id=agent_id,
        workflow_label=workflow_label,
        turns=turns,
        total_duration_ms=total_duration,
        passed=len(turns) > 1,
    )


def main():
    parser = argparse.ArgumentParser(description="Adaptive Conversation Runner (LLM Caller)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--first", type=int, help="Run only first N tests")
    parser.add_argument("--category", type=str, help="Run only one category (A-I)")
    parser.add_argument("--test", type=str, help="Run single test by name prefix")
    args = parser.parse_args()

    agent_id = WORKFLOW_1_AGENT_ID
    if not agent_id or "AGENT_ID" in agent_id:
        print("ERROR: Set WORKFLOW_1_AGENT_ID environment variable.")
        sys.exit(1)

    if not ANTHROPIC_API_KEY:
        print("ERROR: Set ANTHROPIC_API_KEY for the adaptive caller agent.")
        sys.exit(1)

    scenarios = ALL_SCENARIOS
    if args.category:
        cat = args.category.upper()
        scenarios = [s for s in scenarios if s["test_name"].startswith(cat)]
    if args.test:
        prefix = args.test.upper()
        scenarios = [s for s in scenarios if s["test_name"].upper().startswith(prefix)]
    if args.first:
        scenarios = scenarios[:args.first]

    total = len(scenarios)
    if total == 0:
        print("No tests found matching filter.")
        sys.exit(1)

    sevs = Counter(s["severity"] for s in scenarios)

    print("=" * 70)
    print("ADAPTIVE CONVERSATION RUNNER — LLM-POWERED CALLER")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"\nAgent:    {agent_id[:16]}...")
    print(f"Tests:    {total}")
    print(f"Severity: {sevs.get('critical',0)} critical, {sevs.get('high',0)} high, "
          f"{sevs.get('medium',0)} medium, {sevs.get('low',0)} low")
    print(f"Caller:   Claude Haiku (adaptive, real-time responses)")
    print()

    if args.dry_run:
        for s in scenarios:
            sev = SEVERITY_LABELS.get(s["severity"], s["severity"])
            persona = scenario_to_persona(s)
            print(f"  {sev} {s['test_name']}")
            print(f"         Persona: {persona.name} — {persona.goal}")
            print(f"         Behavior: {persona.behavior_notes[:80]}")
        print(f"\n[DRY RUN — no API calls made]")
        return

    results = []
    completed = 0
    empty = 0
    start_time = time.time()

    for i, s in enumerate(scenarios):
        test_name = s["test_name"]
        severity = s["severity"]
        sev_icon = SEVERITY_LABELS.get(severity, severity)
        persona = scenario_to_persona(s)

        print(f"\n[{i+1}/{total}] {sev_icon} {test_name}")
        print(f"  Persona: {persona.name} — {persona.goal}")

        result = run_adaptive_conversation(
            agent_id=agent_id,
            workflow_label="workflow_1",
            test_name=test_name,
            persona=persona,
        )

        print(f"  {'─' * 60}")
        for t in result.turns:
            if t.user_message == "[CONVERSATION_START]":
                print(f"  🤖 GREETING: {t.agent_response[:300]}")
            else:
                print(f"  👤 CALLER: {t.user_message}")
                print(f"  🤖 AGENT:  {t.agent_response[:300]}")
            print(f"     ⏱  {t.latency_ms:.0f}ms")
        print(f"  {'─' * 60}")

        if not result.turns or not result.turns[-1].agent_response:
            print(f"  ⚠️  NO RESPONSE / EMPTY CONVERSATION")
            empty += 1
        else:
            print(f"  ℹ️  Completed ({len(result.turns)} turns, {result.avg_latency_ms:.0f}ms avg)")
            completed += 1

        result_dict = result.to_dict()
        result_dict["_test_metadata"] = {
            "pass_criteria": s["pass_criteria"],
            "severity": s["severity"],
            "context": s.get("context", ""),
            "mode": "adaptive",
            "persona": {
                "name": persona.name,
                "goal": persona.goal,
                "behavior": persona.behavior_notes,
            },
        }
        results.append(result_dict)

        time.sleep(0.3)

    elapsed = time.time() - start_time

    print(f"\n{'═' * 70}")
    print(f"  ADAPTIVE RUN COMPLETE")
    print(f"  {total} tests | {completed} completed | {empty} empty/failed | {elapsed:.0f}s elapsed")
    print(f"{'═' * 70}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "suite": "12_ehr_integration",
        "mode": "adaptive",
        "timestamp": timestamp,
        "elapsed_seconds": round(elapsed, 1),
        "summary": {"total_tests": total, "completed": completed, "empty_failed": empty},
        "results": results,
    }

    outpath = Path(RESULTS_DIR) / f"suite12_adaptive_{timestamp}.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {outpath}")


if __name__ == "__main__":
    main()
