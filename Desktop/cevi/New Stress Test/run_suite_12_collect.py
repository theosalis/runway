#!/usr/bin/env python3
"""
Suite 12 — EHR Integration Stress Test (Transcript Collection Mode)
====================================================================
Runs all 120 EHR integration tests against ElevenLabs agent and saves
FULL transcripts + test metadata to JSON. NO LLM judge needed.

After collection, feed the output JSON to Claude Code for evaluation.

Usage:
  export ELEVENLABS_API_KEY=your_key
  export WORKFLOW_1_AGENT_ID=your_agent_id
  python3 run_suite_12_collect.py

Options:
  --dry-run       Print test plan without executing
  --first N       Run only the first N tests
  --category X    Run only category X (A, B, C, D, E, F, G, H, I)
"""

import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from collections import Counter

from config import WORKFLOW_1_AGENT_ID, RESULTS_DIR
from client import run_conversation_test
from test_12_ehr_integration import ALL_SCENARIOS
from llm_judge import SEVERITY_LABELS


def main():
    parser = argparse.ArgumentParser(description="Suite 12 — Collect Transcripts (No Judge)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--first", type=int, help="Run only first N tests")
    parser.add_argument("--category", type=str, help="Run only one category (A-I)")
    args = parser.parse_args()

    agent_id = WORKFLOW_1_AGENT_ID
    if not agent_id or "AGENT_ID" in agent_id:
        print("ERROR: Set WORKFLOW_1_AGENT_ID environment variable.")
        sys.exit(1)

    # Filter scenarios
    scenarios = ALL_SCENARIOS
    if args.category:
        cat = args.category.upper()
        scenarios = [s for s in scenarios if s["test_name"].startswith(cat)]
        if not scenarios:
            print(f"No tests found for category '{cat}'. Available: A B C D E F G H I")
            sys.exit(1)
    if args.first:
        scenarios = scenarios[:args.first]

    total = len(scenarios)
    sevs = Counter(s["severity"] for s in scenarios)

    print("=" * 70)
    print("SUITE 12 — EHR INTEGRATION (TRANSCRIPT COLLECTION)")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"\nAgent:    {agent_id[:16]}...")
    print(f"Tests:    {total}")
    print(f"Severity: {sevs.get('critical',0)} critical, {sevs.get('high',0)} high, "
          f"{sevs.get('medium',0)} medium, {sevs.get('low',0)} low")
    print(f"Judge:    DISABLED — transcripts saved for external evaluation")
    print()

    if args.dry_run:
        for s in scenarios:
            sev = SEVERITY_LABELS.get(s["severity"], s["severity"])
            print(f"  {sev} {s['test_name']} ({len(s['messages'])} turns)")
            print(f"         Pass: {s['pass_criteria'][:100]}...")
        print(f"\n[DRY RUN — no API calls made]")
        return

    # ─── Run tests ─────────────────────────────────────────────
    results = []
    completed = 0
    empty = 0
    start_time = time.time()

    for i, s in enumerate(scenarios):
        test_name = s["test_name"]
        severity = s["severity"]
        sev_icon = SEVERITY_LABELS.get(severity, severity)

        print(f"\n[{i+1}/{total}] {sev_icon} {test_name}")
        print(f"  Criteria: {s['pass_criteria'][:120]}...")

        result = run_conversation_test(
            agent_id=agent_id,
            workflow_label="workflow_1",
            test_name=test_name,
            messages=s["messages"],
            expected_nodes=s.get("expected_nodes"),
        )

        # Print transcript
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

        # Store result + test metadata for external judging
        result_dict = result.to_dict()
        result_dict["_test_metadata"] = {
            "pass_criteria": s["pass_criteria"],
            "severity": s["severity"],
            "context": s.get("context", ""),
            "expected_nodes": s.get("expected_nodes", []),
            "input_messages": s["messages"],
        }
        results.append(result_dict)

        time.sleep(0.3)

    elapsed = time.time() - start_time

    # ─── Summary ──────────────────────────────────────────────
    print(f"\n{'═' * 70}")
    print(f"  TRANSCRIPT COLLECTION COMPLETE")
    print(f"  {total} tests | {completed} completed | {empty} empty/failed | {elapsed:.0f}s elapsed")
    print(f"{'═' * 70}")

    # ─── Save results with full metadata ──────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "suite": "12_ehr_integration",
        "mode": "transcript_collection",
        "timestamp": timestamp,
        "elapsed_seconds": round(elapsed, 1),
        "summary": {
            "total_tests": total,
            "completed": completed,
            "empty_failed": empty,
        },
        "results": results,
    }

    outpath = Path(RESULTS_DIR) / f"suite12_transcripts_{timestamp}.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {outpath}")
    print(f"  Feed this file to Claude Code for healthcare-professional evaluation.")


if __name__ == "__main__":
    main()
