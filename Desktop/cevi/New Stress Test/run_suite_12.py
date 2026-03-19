#!/usr/bin/env python3
"""
Suite 12 — EHR Integration Stress Test Runner (Standalone)
===========================================================
Runs all 120 EHR integration tests with LLM-as-Judge evaluation.
No dependency on suites 01-11.

Usage:
  export ELEVENLABS_API_KEY=your_key
  export ANTHROPIC_API_KEY=your_key
  export WORKFLOW_1_AGENT_ID=your_agent_id
  python3 run_suite_12.py

Options:
  --dry-run       Print test plan without executing
  --first N       Run only the first N tests (for quick validation)
  --category X    Run only category X (A, B, C, D, E, F, G, H, I)
"""

import sys
import json
import time
import argparse
import os
from datetime import datetime
from pathlib import Path

from config import WORKFLOW_1_AGENT_ID, RESULTS_DIR
from client import run_conversation_test
from test_12_ehr_integration import ALL_SCENARIOS
from llm_judge import judge_conversation, compute_grade, SEVERITY_LABELS, SEVERITY_WEIGHTS


def main():
    parser = argparse.ArgumentParser(description="Suite 12 EHR Stress Test (LLM-Judged)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--first", type=int, help="Run only first N tests")
    parser.add_argument("--category", type=str, help="Run only one category (A-I)")
    args = parser.parse_args()

    agent_id = WORKFLOW_1_AGENT_ID
    if not agent_id or "AGENT_ID" in agent_id:
        print("ERROR: Set WORKFLOW_1_AGENT_ID environment variable.")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY environment variable for LLM judge.")
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

    # Count by severity
    from collections import Counter
    sevs = Counter(s["severity"] for s in scenarios)

    print("=" * 70)
    print("SUITE 12 — EHR INTEGRATION STRESS TEST (LLM-JUDGED)")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"\nAgent:      {agent_id[:16]}...")
    print(f"Tests:      {total}")
    print(f"Severity:   {sevs.get('critical',0)} critical, {sevs.get('high',0)} high, {sevs.get('medium',0)} medium, {sevs.get('low',0)} low")
    print(f"Judge:      Claude Sonnet (evaluates conversation logic, not keywords)")
    print()

    if args.dry_run:
        for s in scenarios:
            sev = SEVERITY_LABELS.get(s["severity"], s["severity"])
            print(f"  {sev} {s['test_name']} ({len(s['messages'])} turns)")
            print(f"         Pass: {s['pass_criteria'][:90]}...")
        print(f"\n[DRY RUN — no API calls made]")
        return

    # ─── Run tests ─────────────────────────────────────────────
    verdicts = []
    results = []
    start_time = time.time()

    for i, s in enumerate(scenarios):
        test_name = s["test_name"]
        severity = s["severity"]
        sev_icon = SEVERITY_LABELS.get(severity, severity)

        print(f"[{i+1}/{total}] {sev_icon} {test_name}...", end=" ", flush=True)

        # Run conversation against ElevenLabs agent
        result = run_conversation_test(
            agent_id=agent_id,
            workflow_label="workflow_1",
            test_name=test_name,
            messages=s["messages"],
            expected_nodes=s.get("expected_nodes"),
        )
        results.append(result)

        # Print transcript
        print()
        print(f"       {'─' * 55}")
        for t in result.turns:
            if t.user_message == "[CONVERSATION_START]":
                print(f"       🤖 GREETING: {t.agent_response[:250]}")
            else:
                print(f"       👤 CALLER: {t.user_message}")
                print(f"       🤖 AGENT:  {t.agent_response[:250]}")
            print(f"          ⏱  {t.latency_ms:.0f}ms")
        print(f"       {'─' * 55}")

        # LLM Judge evaluation
        if result.turns:
            verdict = judge_conversation(
                test_name=test_name,
                turns=result.turns,
                pass_criteria=s["pass_criteria"],
                severity=severity,
                context=s.get("context", ""),
            )
        else:
            from llm_judge import JudgeVerdict
            verdict = JudgeVerdict(
                test_name=test_name, passed=False, confidence=0,
                severity=severity,
                reasoning="No conversation turns — agent did not respond",
                violations=["Empty conversation"], mitigating_factors=[],
                weighted_score=SEVERITY_WEIGHTS.get(severity, 3),
            )

        verdicts.append(verdict)

        icon = "✅" if verdict.passed else "❌"
        print(f"       {icon} VERDICT: {'PASS' if verdict.passed else 'FAIL'} ({verdict.confidence}% confidence)")
        print(f"       Judge: {verdict.reasoning}")
        if verdict.violations:
            for v in verdict.violations:
                print(f"         • {v}")
        if verdict.mitigating_factors:
            for m in verdict.mitigating_factors:
                print(f"         ✓ {m}")
        print()

        time.sleep(0.3)  # Small delay between tests

    elapsed = time.time() - start_time

    # ─── Grade Report ──────────────────────────────────────────
    grade = compute_grade(verdicts)

    print(f"\n{'═' * 70}")
    print(f"  REPORT CARD — Suite 12: EHR Integration")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {elapsed:.0f}s elapsed")
    print(f"{'═' * 70}")
    print()
    print(f"  ┌─────────────────────────────────────────────┐")
    print(f"  │  GRADE:  {grade['letter_grade']:>4}      SCORE: {grade['numeric_score']:>5.1f} / 100  │")
    print(f"  │  Tests:  {grade['total_tests']:<4}  Pass: {grade['total_passed']:<4}  Fail: {grade['total_failed']:<5} │")
    print(f"  └─────────────────────────────────────────────┘")

    if grade.get("critical_failures"):
        print(f"\n  🔴 AUTOMATIC F — Critical failures:")
        for cf in grade["critical_failures"]:
            print(f"     ✗ {cf}")

    print(f"\n  SEVERITY BREAKDOWN:")
    for sev in ["critical", "high", "medium", "low"]:
        if sev in grade.get("breakdown_by_severity", {}):
            b = grade["breakdown_by_severity"][sev]
            icon = SEVERITY_LABELS.get(sev, sev)
            filled = "█" * b["passed"]
            empty = "░" * b["failed"]
            print(f"    {icon:<16} {b['passed']}/{b['total']} passed ({b['pass_rate']})  {filled}{empty}")

    print(f"\n  ALL VERDICTS:")
    for v in verdicts:
        icon = "✅" if v.passed else "❌"
        sev = SEVERITY_LABELS.get(v.severity, v.severity)
        line = f"    {icon} {sev} {v.test_name}"
        if not v.passed:
            line += f"\n       ↳ {v.reasoning}"
        print(line)

    # ─── Save results ──────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "suite": "12_ehr_integration",
        "timestamp": timestamp,
        "elapsed_seconds": round(elapsed, 1),
        "grade": grade,
        "verdicts": [v.to_dict() for v in verdicts],
        "results": [r.to_dict() for r in results],
    }

    outpath = Path(RESULTS_DIR) / f"suite12_{timestamp}.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {outpath}")

    # Exit code
    sys.exit(1 if grade["total_failed"] > 0 else 0)


if __name__ == "__main__":
    main()
