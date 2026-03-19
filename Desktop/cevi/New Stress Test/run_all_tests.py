#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ElevenLabs Conversational AI — Full Stress Test Runner
=======================================================
Runs all 12 test suites against both Workflow 1 and Workflow 2.
Suite 12 (EHR Integration) uses LLM-as-Judge for pass/fail evaluation
instead of keyword matching — analyzes conversation flow and logic.

Usage:
  export ELEVENLABS_API_KEY=your_key
  export WORKFLOW_1_AGENT_ID=agent_id_for_workflow_1
  export WORKFLOW_2_AGENT_ID=agent_id_for_workflow_2
  export ANTHROPIC_API_KEY=your_anthropic_key    # Required for LLM judge
  python run_all_tests.py

Options:
  --wf1-only          Run only against Workflow 1
  --wf2-only          Run only against Workflow 2
  --suite 04          Run only test suite 04 (medication)
  --suite 12          Run only suite 12 (EHR Integration, LLM-judged)
  --dry-run           Print test plan without executing
  --parallel          Run both workflows in parallel (faster, more API load)
  --skip-judge        Run suite 12 without LLM judge (keyword fallback only)
"""

import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path

from config import (
    WORKFLOW_1_AGENT_ID,
    WORKFLOW_2_AGENT_ID,
    RESULTS_DIR,
)
from client import run_conversation_test

# Import all test suites (1-11: original, 12: EHR integration)
from test_01_crisis_emergency import ALL_SCENARIOS as SUITE_01
from test_02_crisis_urgency import ALL_SCENARIOS as SUITE_02
from test_03_new_patient import ALL_SCENARIOS as SUITE_03
from test_04_medication import ALL_SCENARIOS as SUITE_04
from test_05_cancel_reschedule import ALL_SCENARIOS as SUITE_05
from test_06_telehealth import ALL_SCENARIOS as SUITE_06
from test_07_insurance_billing_npi import ALL_SCENARIOS as SUITE_07
from test_08_existing_faq_family import ALL_SCENARIOS as SUITE_08
from test_09_edge_cases import ALL_SCENARIOS as SUITE_09
from test_10_latency_benchmarks import ALL_SCENARIOS as SUITE_10, LATENCY_REPEAT_COUNT
from test_11_adversarial_edge_cases import ALL_SCENARIOS as SUITE_11
from test_12_ehr_integration import ALL_SCENARIOS as SUITE_12

# LLM Judge for Suite 12
from llm_judge import judge_conversation, compute_grade, SEVERITY_LABELS

TEST_SUITES = {
    "01_crisis_emergency": SUITE_01,
    "02_crisis_urgency": SUITE_02,
    "03_new_patient": SUITE_03,
    "04_medication": SUITE_04,
    "05_cancel_reschedule": SUITE_05,
    "06_telehealth": SUITE_06,
    "07_insurance_billing_npi": SUITE_07,
    "08_existing_faq_family": SUITE_08,
    "09_edge_cases": SUITE_09,
    "10_latency_benchmarks": SUITE_10,
    "11_adversarial_edge_cases": SUITE_11,
    "12_ehr_integration": SUITE_12,
}

# Suites that use LLM judge instead of keyword validators
LLM_JUDGED_SUITES = {"12_ehr_integration"}


def run_suite(suite_name: str, scenarios: list, agent_id: str, wf_label: str, skip_judge: bool = False) -> tuple:
    """
    Run all scenarios in a suite against one workflow.
    Returns (results, verdicts) — verdicts is populated only for LLM-judged suites.
    """
    results = []
    verdicts = []
    total = len(scenarios)
    is_judged = suite_name in LLM_JUDGED_SUITES and not skip_judge

    for i, scenario in enumerate(scenarios):
        test_name = scenario["test_name"]
        severity = scenario.get("severity", "medium")
        sev_icon = SEVERITY_LABELS.get(severity, severity)
        print(f"  [{i+1}/{total}] {sev_icon} {test_name}...", end=" ", flush=True)

        # Latency benchmarks run multiple times
        if suite_name == "10_latency_benchmarks":
            repeat_results = []
            for r in range(LATENCY_REPEAT_COUNT):
                result = run_conversation_test(
                    agent_id=agent_id,
                    workflow_label=wf_label,
                    test_name=f"{test_name}_run{r+1}",
                    messages=scenario["messages"],
                    expected_nodes=scenario.get("expected_nodes"),
                    validators=scenario.get("validators"),
                )
                repeat_results.append(result)
                time.sleep(0.5)

            avg_latency = sum(r.avg_latency_ms for r in repeat_results) / len(repeat_results)
            any_passed = any(r.passed for r in repeat_results)
            pass_rate = sum(1 for r in repeat_results if r.passed) / len(repeat_results)

            result = repeat_results[0]
            result.test_name = test_name
            result.failure_reason = (
                None if any_passed
                else f"Failed all {LATENCY_REPEAT_COUNT} runs. Last: {repeat_results[-1].failure_reason}"
            )
            result.passed = pass_rate >= 0.5

            print(f"{'PASS' if result.passed else 'FAIL'} "
                  f"(avg {avg_latency:.0f}ms, {pass_rate*100:.0f}% pass rate)")
        else:
            # Run the conversation
            result = run_conversation_test(
                agent_id=agent_id,
                workflow_label=wf_label,
                test_name=test_name,
                messages=scenario["messages"],
                expected_nodes=scenario.get("expected_nodes"),
                validators=scenario.get("validators"),
            )

            # ─── LLM JUDGE EVALUATION ─────────────────────────
            if is_judged and result.turns:
                verdict = judge_conversation(
                    test_name=test_name,
                    turns=result.turns,
                    pass_criteria=scenario.get("pass_criteria", ""),
                    severity=severity,
                    context=scenario.get("context", ""),
                )
                verdicts.append(verdict)

                # Override the keyword-based pass/fail with LLM verdict
                result.passed = verdict.passed
                result.failure_reason = None if verdict.passed else verdict.reasoning

                status = "✅ PASS" if verdict.passed else "❌ FAIL"
                conf = f"({verdict.confidence}% conf)"
                print(f"{status} {conf} ({result.avg_latency_ms:.0f}ms avg)")

                if not verdict.passed:
                    print(f"       ↳ Judge: {verdict.reasoning}")
                    if verdict.violations:
                        for v in verdict.violations:
                            print(f"         • {v}")
                if verdict.mitigating_factors:
                    for m in verdict.mitigating_factors:
                        print(f"         ✓ {m}")
            else:
                # Non-judged suites: use keyword validators as before
                status = "PASS" if result.passed else "FAIL"
                print(f"{status} ({result.avg_latency_ms:.0f}ms avg)")
                if not result.passed:
                    print(f"       ↳ {result.failure_reason}")

            # Print full transcript for every test
            print(f"\n       {'─' * 60}")
            for t in result.turns:
                if t.user_message == "[CONVERSATION_START]":
                    print(f"       🤖 AGENT (greeting): {t.agent_response[:300]}")
                    print(f"          ⏱  {t.latency_ms:.0f}ms")
                else:
                    print(f"       👤 CALLER: {t.user_message}")
                    print(f"       🤖 AGENT:  {t.agent_response[:300]}")
                    print(f"          ⏱  {t.latency_ms:.0f}ms")
                    if t.error:
                        print(f"          ⚠️  {t.error}")
            print(f"       {'─' * 60}\n")

        results.append(result)

    return results, verdicts


def print_summary(all_results: dict, all_verdicts: dict):
    """Print a summary comparison table with LLM judge grades."""
    print("\n" + "=" * 90)
    print("STRESS TEST SUMMARY")
    print("=" * 90)

    for wf_label in ["workflow_1", "workflow_2"]:
        if wf_label not in all_results:
            continue

        results = all_results[wf_label]
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed

        latencies = [r.avg_latency_ms for r in results if r.turns]
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        max_lat = max(latencies) if latencies else 0
        p95_vals = sorted(latencies)
        p95_lat = p95_vals[int(len(p95_vals) * 0.95)] if p95_vals else 0

        print(f"\n{'─' * 45}")
        print(f"  {wf_label.upper().replace('_', ' ')}")
        print(f"{'─' * 45}")
        print(f"  Tests:     {total} total, {passed} passed, {failed} failed")
        print(f"  Pass Rate: {passed/total*100:.1f}%")
        print(f"  Latency:   avg={avg_lat:.0f}ms  max={max_lat:.0f}ms  p95={p95_lat:.0f}ms")

        if failed > 0:
            print(f"\n  FAILURES:")
            for r in results:
                if not r.passed:
                    print(f"    ✗ {r.test_name}: {r.failure_reason}")

    # ─── LLM JUDGE GRADE REPORT ───────────────────────────────
    for wf_label in ["workflow_1", "workflow_2"]:
        if wf_label not in all_verdicts or not all_verdicts[wf_label]:
            continue

        verdicts = all_verdicts[wf_label]
        grade = compute_grade(verdicts)

        print(f"\n{'═' * 90}")
        print(f"  LLM JUDGE REPORT CARD — {wf_label.upper().replace('_', ' ')} (Suite 12: EHR Integration)")
        print(f"{'═' * 90}")
        print(f"")
        print(f"  ┌─────────────────────────────────────────┐")
        print(f"  │  GRADE:  {grade['letter_grade']:>4}    SCORE: {grade['numeric_score']:>5.1f}/100  │")
        print(f"  │  Tests:  {grade['total_tests']}   Pass: {grade['total_passed']}   Fail: {grade['total_failed']:<5} │")
        print(f"  └─────────────────────────────────────────┘")

        if grade.get("critical_failures"):
            print(f"\n  🔴 AUTOMATIC F — Critical failures detected:")
            for cf in grade["critical_failures"]:
                print(f"     ✗ {cf}")

        print(f"\n  BREAKDOWN BY SEVERITY:")
        for sev in ["critical", "high", "medium", "low"]:
            if sev in grade.get("breakdown_by_severity", {}):
                b = grade["breakdown_by_severity"][sev]
                icon = SEVERITY_LABELS.get(sev, sev)
                bar_total = b["total"]
                bar_pass = b["passed"]
                filled = "█" * bar_pass
                empty = "░" * (bar_total - bar_pass)
                print(f"    {icon:<16} {bar_pass}/{bar_total} passed ({b['pass_rate']})  {filled}{empty}")

        # Detailed verdicts list
        print(f"\n  DETAILED VERDICTS:")
        for v in verdicts:
            icon = "✅" if v.passed else "❌"
            sev = SEVERITY_LABELS.get(v.severity, v.severity)
            print(f"    {icon} {sev} {v.test_name}")
            if not v.passed:
                print(f"       ↳ {v.reasoning}")
                for viol in v.violations:
                    print(f"         • {viol}")

    # Side-by-side comparison if both ran
    if "workflow_1" in all_results and "workflow_2" in all_results:
        print(f"\n{'=' * 90}")
        print("LATENCY COMPARISON (Workflow 1 vs Workflow 2)")
        print(f"{'=' * 90}")
        print(f"{'Test':<45} {'WF1 (ms)':>10} {'WF2 (ms)':>10} {'Delta':>10}")
        print(f"{'─' * 75}")

        wf1_by_name = {r.test_name: r for r in all_results["workflow_1"]}
        wf2_by_name = {r.test_name: r for r in all_results["workflow_2"]}

        for name in wf1_by_name:
            if name in wf2_by_name:
                l1 = wf1_by_name[name].avg_latency_ms
                l2 = wf2_by_name[name].avg_latency_ms
                delta = l2 - l1
                arrow = "→ WF2 slower" if delta > 50 else ("→ WF1 slower" if delta < -50 else "≈")
                print(f"  {name:<43} {l1:>8.0f}ms {l2:>8.0f}ms {delta:>+8.0f}ms {arrow}")


def save_results(all_results: dict, all_verdicts: dict, timestamp: str):
    """Save detailed JSON results including LLM judge verdicts."""
    for wf_label, results in all_results.items():
        # Standard results
        output = {
            "workflow": wf_label,
            "timestamp": timestamp,
            "total_tests": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [r.to_dict() for r in results],
        }

        # Append LLM judge data if available
        if wf_label in all_verdicts and all_verdicts[wf_label]:
            verdicts = all_verdicts[wf_label]
            grade = compute_grade(verdicts)
            output["llm_judge"] = {
                "grade": grade,
                "verdicts": [v.to_dict() for v in verdicts],
            }

        filepath = Path(RESULTS_DIR) / f"{wf_label}_{timestamp}.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="ElevenLabs Stress Test Runner")
    parser.add_argument("--wf1-only", action="store_true", help="Run only Workflow 1")
    parser.add_argument("--wf2-only", action="store_true", help="Run only Workflow 2")
    parser.add_argument("--suite", type=str, help="Run only specific suite (e.g., '04' or '12')")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--skip-judge", action="store_true", help="Skip LLM judge for suite 12")
    args = parser.parse_args()

    # Determine which workflows to test
    workflows = {}
    if not args.wf2_only:
        workflows["workflow_1"] = WORKFLOW_1_AGENT_ID
    if not args.wf1_only:
        workflows["workflow_2"] = WORKFLOW_2_AGENT_ID

    # Determine which suites to run
    suites_to_run = TEST_SUITES
    if args.suite:
        matching = {k: v for k, v in TEST_SUITES.items() if args.suite in k}
        if not matching:
            print(f"No suite matching '{args.suite}'. Available: {list(TEST_SUITES.keys())}")
            sys.exit(1)
        suites_to_run = matching

    # Check for ANTHROPIC_API_KEY if running judged suites
    import os
    if any(s in LLM_JUDGED_SUITES for s in suites_to_run) and not args.skip_judge:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("⚠️  WARNING: ANTHROPIC_API_KEY not set. LLM judge will not work.")
            print("   Set it with: export ANTHROPIC_API_KEY=your_key")
            print("   Or run with --skip-judge to use keyword fallback.\n")

    # Count total tests
    total_scenarios = sum(len(s) for s in suites_to_run.values())
    total_runs = total_scenarios * len(workflows)

    print("=" * 90)
    print("ELEVENLABS CONVERSATIONAL AI — STRESS TEST")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 90)
    print(f"\nWorkflows:  {', '.join(workflows.keys())}")
    print(f"Suites:     {len(suites_to_run)} ({', '.join(suites_to_run.keys())})")
    print(f"Scenarios:  {total_scenarios} per workflow")
    print(f"Total runs: {total_runs}")

    judged = [s for s in suites_to_run if s in LLM_JUDGED_SUITES]
    if judged and not args.skip_judge:
        print(f"LLM Judge:  Active for {', '.join(judged)} (Claude Sonnet evaluates each transcript)")
    print()

    if args.dry_run:
        for suite_name, scenarios in suites_to_run.items():
            is_judged = suite_name in LLM_JUDGED_SUITES
            judge_tag = " [LLM-JUDGED]" if is_judged else ""
            print(f"\n  Suite: {suite_name}{judge_tag}")
            for s in scenarios:
                sev = s.get("severity", "—")
                print(f"    - [{sev:>8}] {s['test_name']} ({len(s['messages'])} turns)")
                if is_judged and "pass_criteria" in s:
                    print(f"               Pass: {s['pass_criteria'][:100]}...")
        print(f"\n[DRY RUN — no API calls made]")
        return

    # Validate API keys
    for wf_label, agent_id in workflows.items():
        if "YOUR_" in agent_id or "AGENT_ID" in agent_id:
            print(f"ERROR: Set {wf_label.upper()}_AGENT_ID environment variable.")
            sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = {}
    all_verdicts = {}

    for wf_label, agent_id in workflows.items():
        print(f"\n{'━' * 90}")
        print(f"  RUNNING: {wf_label.upper()} (Agent: {agent_id[:12]}...)")
        print(f"{'━' * 90}")

        wf_results = []
        wf_verdicts = []
        for suite_name, scenarios in suites_to_run.items():
            is_judged = suite_name in LLM_JUDGED_SUITES and not args.skip_judge
            judge_tag = " 🧠 LLM-JUDGED" if is_judged else ""
            print(f"\n  ── Suite: {suite_name} ({len(scenarios)} scenarios){judge_tag} ──")

            suite_results, suite_verdicts = run_suite(
                suite_name, scenarios, agent_id, wf_label,
                skip_judge=args.skip_judge,
            )
            wf_results.extend(suite_results)
            wf_verdicts.extend(suite_verdicts)

        all_results[wf_label] = wf_results
        all_verdicts[wf_label] = wf_verdicts

    # Summary, grade report, and save
    print_summary(all_results, all_verdicts)
    save_results(all_results, all_verdicts, timestamp)

    # Exit code
    total_failed = sum(
        sum(1 for r in results if not r.passed)
        for results in all_results.values()
    )
    sys.exit(1 if total_failed > 0 else 0)


if __name__ == "__main__":
    main()
