#!/usr/bin/env python3
"""
Suite 12 — EHR Integration Stress Test Runner (Transcript-Only Mode)
=====================================================================
Runs tests and prints full transcripts. LLM judge is DISABLED.
When ready to grade, run run_suite_12.py instead.

Usage:
  python3 run_suite_12_transcripts.py
  python3 run_suite_12_transcripts.py --first 5
  python3 run_suite_12_transcripts.py --category A
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
    parser = argparse.ArgumentParser(description="Suite 12 — Transcript Only (No Judge)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--first", type=int)
    parser.add_argument("--category", type=str)
    args = parser.parse_args()

    agent_id = WORKFLOW_1_AGENT_ID
    if not agent_id or "AGENT_ID" in agent_id:
        print("ERROR: Set WORKFLOW_1_AGENT_ID environment variable.")
        sys.exit(1)

    scenarios = ALL_SCENARIOS
    if args.category:
        cat = args.category.upper()
        scenarios = [s for s in scenarios if s["test_name"].startswith(cat)]
    if args.first:
        scenarios = scenarios[:args.first]

    total = len(scenarios)
    sevs = Counter(s["severity"] for s in scenarios)

    print("=" * 70)
    print("SUITE 12 — EHR INTEGRATION (TRANSCRIPT MODE — NO JUDGE)")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"\nAgent:    {agent_id[:16]}...")
    print(f"Tests:    {total}")
    print(f"Severity: {sevs.get('critical',0)} critical, {sevs.get('high',0)} high, {sevs.get('medium',0)} medium, {sevs.get('low',0)} low")
    print(f"Judge:    DISABLED (transcript-only mode)")
    print()

    if args.dry_run:
        for s in scenarios:
            sev = SEVERITY_LABELS.get(s["severity"], s["severity"])
            print(f"  {sev} {s['test_name']} ({len(s['messages'])} msgs)")
        print(f"\n[DRY RUN]")
        return

    passed = 0
    failed = 0
    start_time = time.time()

    for i, s in enumerate(scenarios):
        test_name = s["test_name"]
        severity = s["severity"]
        sev_icon = SEVERITY_LABELS.get(severity, severity)

        print(f"\n[{i+1}/{total}] {sev_icon} {test_name}")
        print(f"  Pass criteria: {s['pass_criteria'][:120]}...")
        print(f"  Context: {s.get('context', '')[:120]}")
        print()

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
            failed += 1
        else:
            print(f"  ℹ️  Conversation completed ({len(result.turns)} turns, {result.avg_latency_ms:.0f}ms avg)")
            # Not grading — just counting completions
            passed += 1

        time.sleep(0.3)

    elapsed = time.time() - start_time

    print(f"\n{'═' * 70}")
    print(f"  TRANSCRIPT RUN COMPLETE")
    print(f"  {total} tests | {passed} completed | {failed} empty/failed | {elapsed:.0f}s elapsed")
    print(f"  Judge was DISABLED — run run_suite_12.py for graded verdicts")
    print(f"{'═' * 70}")

    # Save transcripts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = Path(RESULTS_DIR) / f"suite12_transcripts_{timestamp}.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    # We don't have results stored in a list in this version, just print notification
    print(f"\n  To save results with verdicts, add Anthropic credits and run run_suite_12.py")


if __name__ == "__main__":
    main()
