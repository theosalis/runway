#!/usr/bin/env python3
"""
V2 Parallel Runner — All 85 Tests with LLM Caller + LLM Judge
================================================================
Runs the v2 workflow-node test suite in parallel using:
  - Claude Haiku as the caller agent (dynamic, realistic responses)
  - Claude Sonnet as the LLM judge (evaluates against pass criteria + EHR ground truth)
  - Async WebSocket connections for parallel execution

Usage:
  export ELEVENLABS_API_KEY=your_key
  export WORKFLOW_1_AGENT_ID=your_agent_id
  export ANTHROPIC_API_KEY=your_key

  python3 run_v2_parallel.py                          # All 85 tests, 20 concurrent
  python3 run_v2_parallel.py --concurrency 10         # 10 concurrent
  python3 run_v2_parallel.py --node med_refill        # Single node
  python3 run_v2_parallel.py --severity critical      # Only critical tests
  python3 run_v2_parallel.py --tag v1_regression      # Only v1 regression retests
  python3 run_v2_parallel.py --first 5                # First 5 tests
  python3 run_v2_parallel.py --no-judge               # Skip LLM judge (transcripts only)
  python3 run_v2_parallel.py --dry-run                # Print plan
"""

import sys
import os
import json
import asyncio
import time
import argparse
from datetime import datetime
from pathlib import Path
from collections import Counter

from config import (
    WORKFLOW_1_AGENT_ID,
    RESULTS_DIR,
    TURN_TIMEOUT_SECONDS,
)

from test_v2_workflow_nodes import (
    ALL_SCENARIOS,
    SCENARIOS_BY_NODE,
    scenario_to_persona,
    get_judge_context,
)
from caller_agent import CallerPersona, generate_caller_response
from client import TurnResult, ConversationResult
from llm_judge import (
    judge_conversation,
    compute_grade,
    JudgeVerdict,
    SEVERITY_LABELS,
    SEVERITY_WEIGHTS,
)

try:
    import aiohttp
    from websockets import connect as ws_async_connect
    from websockets.exceptions import ConnectionClosed
    from async_client import (
        async_get_signed_url,
        async_wait_for_agent_response,
    )
    HAS_ASYNC = True
except ImportError as e:
    HAS_ASYNC = False
    MISSING_DEP = str(e)


# ─── Adaptive Async Conversation (v2 format) ──────────────────────────

async def run_v2_adaptive_conversation(
    agent_id: str,
    scenario: dict,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    stagger_delay: float = 0.0,
) -> ConversationResult:
    """
    Run a single v2 scenario using async WebSocket + LLM caller.
    Returns ConversationResult with full transcript for judge evaluation.
    """
    test_name = scenario["test_name"]
    persona = scenario_to_persona(scenario)

    await asyncio.sleep(stagger_delay)

    async with semaphore:
        total_start = time.perf_counter()
        turns = []
        conversation_history = []

        # Get signed URL
        url_result = await async_get_signed_url(agent_id, session)
        if not url_result.get("success"):
            return ConversationResult(
                test_name=test_name, agent_id=agent_id,
                workflow_label=scenario["workflow_node"],
                turns=[], total_duration_ms=(time.perf_counter() - total_start) * 1000,
                passed=False,
                failure_reason=f"Signed URL failed: {url_result.get('error')}",
                expected_nodes=scenario.get("expected_path", []),
            )

        signed_url = url_result["signed_url"]

        try:
            async with ws_async_connect(
                signed_url, close_timeout=5, open_timeout=15,
            ) as ws:
                # Initiate text-only conversation
                await ws.send(json.dumps({
                    "type": "conversation_initiation_client_data",
                    "conversation_config_override": {
                        "conversation": {"text_only": True}
                    },
                }))

                # Collect greeting
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

                max_turns = persona.max_turns or 15

                for i in range(max_turns):
                    # Generate caller response via Claude Haiku (blocking → thread)
                    caller_resp = await asyncio.to_thread(
                        generate_caller_response,
                        persona,
                        conversation_history,
                        i,
                    )
                    conversation_history.append({"role": "caller", "text": caller_resp.message})

                    # Send to agent
                    await ws.send(json.dumps({
                        "type": "user_message",
                        "text": caller_resp.message,
                    }))

                    # Wait for agent response
                    agent_text, latency, tools = await async_wait_for_agent_response(
                        ws, timeout=TURN_TIMEOUT_SECONDS,
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

        except ConnectionClosed:
            pass
        except Exception as e:
            if len(turns) < 2:
                return ConversationResult(
                    test_name=test_name, agent_id=agent_id,
                    workflow_label=scenario["workflow_node"],
                    turns=turns,
                    total_duration_ms=(time.perf_counter() - total_start) * 1000,
                    passed=False,
                    failure_reason=f"Exception: {e}",
                    expected_nodes=scenario.get("expected_path", []),
                )

        total_duration = (time.perf_counter() - total_start) * 1000
        return ConversationResult(
            test_name=test_name,
            agent_id=agent_id,
            workflow_label=scenario["workflow_node"],
            turns=turns,
            total_duration_ms=total_duration,
            passed=len(turns) > 1,
            expected_nodes=scenario.get("expected_path", []),
        )


# ─── Parallel Batch Runner ────────────────────────────────────────────

async def run_v2_batch(
    agent_id: str,
    scenarios: list,
    concurrency: int = 20,
    stagger_rate: float = 5.0,
    progress_callback=None,
) -> list:
    """Run all v2 scenarios in parallel. Returns list of ConversationResults."""
    semaphore = asyncio.Semaphore(concurrency)
    completed_count = 0
    lock = asyncio.Lock()
    total = len(scenarios)

    async def run_one(scenario, index, session):
        nonlocal completed_count
        delay = index / stagger_rate
        result = await run_v2_adaptive_conversation(
            agent_id=agent_id,
            scenario=scenario,
            session=session,
            semaphore=semaphore,
            stagger_delay=delay,
        )
        async with lock:
            completed_count += 1
            current = completed_count
        if progress_callback:
            progress_callback(current, total, result, scenario)
        return result

    connector = aiohttp.TCPConnector(limit=concurrency + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [run_one(s, i, session) for i, s in enumerate(scenarios)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Clean up exceptions
    clean = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            clean.append(ConversationResult(
                test_name=scenarios[i]["test_name"],
                agent_id=agent_id,
                workflow_label=scenarios[i]["workflow_node"],
                turns=[], total_duration_ms=0, passed=False,
                failure_reason=f"Exception: {r}",
            ))
        else:
            clean.append(r)
    return clean


# ─── Judge All Results ────────────────────────────────────────────────

def judge_all_results(
    results: list,
    scenarios: list,
    progress_callback=None,
) -> list:
    """Run LLM judge on all conversation results. Returns list of JudgeVerdicts."""
    verdicts = []
    total = len(results)

    for i, (result, scenario) in enumerate(zip(results, scenarios)):
        if not result.turns or len(result.turns) < 2:
            verdict = JudgeVerdict(
                test_name=scenario["test_name"],
                passed=False,
                confidence=95,
                severity=scenario["severity"],
                reasoning="Conversation had fewer than 2 turns — likely connection failure or empty response.",
                violations=["Conversation too short / connection failure"],
                mitigating_factors=[],
                weighted_score=SEVERITY_WEIGHTS.get(scenario["severity"], 3),
            )
        else:
            judge_ctx = get_judge_context(scenario)
            verdict = judge_conversation(
                test_name=scenario["test_name"],
                turns=result.turns,
                pass_criteria=scenario["pass_criteria"],
                severity=scenario["severity"],
                context=judge_ctx,
            )

        verdicts.append(verdict)
        if progress_callback:
            progress_callback(i + 1, total, verdict)

    return verdicts


# ─── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="V2 Parallel Runner — 85 Tests with LLM Caller + LLM Judge"
    )
    parser.add_argument("--concurrency", type=int, default=20,
                        help="Max simultaneous conversations (default: 20)")
    parser.add_argument("--stagger-rate", type=float, default=5.0,
                        help="New connections per second (default: 5)")
    parser.add_argument("--node", type=str,
                        help="Run only one workflow node (e.g., med_refill, crisis_emergency)")
    parser.add_argument("--severity", type=str,
                        choices=["critical", "high", "medium", "low"],
                        help="Run only tests of a specific severity")
    parser.add_argument("--tag", type=str,
                        help="Run only tests with a specific tag (e.g., v1_regression, happy_path)")
    parser.add_argument("--test", type=str,
                        help="Run single test by test_id prefix (e.g., WF31_01)")
    parser.add_argument("--first", type=int,
                        help="Run only first N tests")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM judge — collect transcripts only")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing")
    args = parser.parse_args()

    # ── Validate environment ──
    if not HAS_ASYNC:
        print(f"ERROR: Missing dependency: {MISSING_DEP}")
        print("Run: pip install aiohttp websockets")
        sys.exit(1)

    agent_id = WORKFLOW_1_AGENT_ID
    if not agent_id or "AGENT_ID" in agent_id:
        print("ERROR: Set WORKFLOW_1_AGENT_ID environment variable.")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY for LLM caller + judge.")
        sys.exit(1)

    # ── Filter scenarios ──
    scenarios = list(ALL_SCENARIOS)

    if args.node:
        scenarios = [s for s in scenarios if s["workflow_node"] == args.node]
    if args.severity:
        scenarios = [s for s in scenarios if s["severity"] == args.severity]
    if args.tag:
        scenarios = [s for s in scenarios if args.tag in s.get("tags", [])]
    if args.test:
        prefix = args.test.upper()
        scenarios = [s for s in scenarios if s["test_id"].upper().startswith(prefix)]
    if args.first:
        scenarios = scenarios[:args.first]

    if not scenarios:
        print("No tests found matching filter.")
        sys.exit(1)

    total = len(scenarios)
    sevs = Counter(s["severity"] for s in scenarios)
    nodes = Counter(s["workflow_node"] for s in scenarios)
    v1_regs = sum(1 for s in scenarios if s.get("v1_regression"))

    # ── Print plan ──
    print("=" * 70)
    print("V2 PARALLEL RUNNER — LLM CALLER + LLM JUDGE")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"\n  Agent:        {agent_id[:20]}...")
    print(f"  Tests:        {total}")
    print(f"  Concurrency:  {args.concurrency}")
    print(f"  Stagger:      {args.stagger_rate} conn/sec")
    print(f"  Caller:       Claude Haiku (adaptive, real-time)")
    print(f"  Judge:        {'DISABLED' if args.no_judge else 'Claude Sonnet (LLM judge)'}")
    print(f"  Severity:     {sevs.get('critical',0)} critical, {sevs.get('high',0)} high, "
          f"{sevs.get('medium',0)} medium, {sevs.get('low',0)} low")
    print(f"  Nodes:        {len(nodes)} workflow nodes")
    print(f"  v1 regressions: {v1_regs}")

    est_conv_time = total / args.stagger_rate + 45  # ~45s avg conversation
    est_judge_time = total * 3 if not args.no_judge else 0  # ~3s per judge call
    est_total = est_conv_time + est_judge_time
    print(f"\n  Est. time:    ~{est_total:.0f}s ({est_total/60:.1f} min)")
    print(f"    Conversations: ~{est_conv_time:.0f}s")
    if not args.no_judge:
        print(f"    Judge calls:   ~{est_judge_time:.0f}s")
    print()

    if args.dry_run:
        for s in scenarios:
            sev = SEVERITY_LABELS.get(s["severity"], s["severity"])
            tags = ", ".join(s.get("tags", []))
            v1 = f" [retests v1 {s['v1_regression']}]" if s.get("v1_regression") else ""
            print(f"  {sev} {s['test_id']:<12} {s['workflow_node']:<30} [{tags}]{v1}")
        print(f"\n  [DRY RUN — no API calls made]")
        return

    # ── Phase 1: Run conversations in parallel ──
    print(f"\n{'─' * 70}")
    print(f"  PHASE 1: Running {total} conversations (parallel, adaptive)")
    print(f"{'─' * 70}")

    pass_count = [0]
    fail_count = [0]

    def conv_progress(completed, total_count, result, scenario):
        turns = len(result.turns)
        avg_ms = result.avg_latency_ms
        status = "✅" if result.turns and len(result.turns) > 1 else "⚠️ "
        pct = completed / total_count * 100
        if result.turns and len(result.turns) > 1:
            pass_count[0] += 1
        else:
            fail_count[0] += 1
        print(f"  [{completed:>3}/{total_count}] {pct:>5.1f}% {status} "
              f"{result.test_name:<50} {turns:>2}t {avg_ms:>5.0f}ms")

    conv_start = time.time()
    results = asyncio.run(run_v2_batch(
        agent_id=agent_id,
        scenarios=scenarios,
        concurrency=args.concurrency,
        stagger_rate=args.stagger_rate,
        progress_callback=conv_progress,
    ))
    conv_elapsed = time.time() - conv_start

    conv_completed = sum(1 for r in results if r.turns and len(r.turns) > 1)
    conv_empty = total - conv_completed

    print(f"\n  Phase 1 complete: {conv_completed} completed, {conv_empty} empty/failed "
          f"({conv_elapsed:.0f}s)")

    # ── Phase 2: Judge all results ──
    verdicts = []
    judge_elapsed = 0.0

    if not args.no_judge:
        print(f"\n{'─' * 70}")
        print(f"  PHASE 2: Judging {total} transcripts (Claude Sonnet)")
        print(f"{'─' * 70}")

        def judge_progress(completed, total_count, verdict):
            status = "✅ PASS" if verdict.passed else "❌ FAIL"
            sev = SEVERITY_LABELS.get(verdict.severity, verdict.severity)
            pct = completed / total_count * 100
            print(f"  [{completed:>3}/{total_count}] {pct:>5.1f}% {status} "
                  f"{sev} {verdict.test_name:<40} "
                  f"(confidence: {verdict.confidence}%)")

        judge_start = time.time()
        verdicts = judge_all_results(results, scenarios, progress_callback=judge_progress)
        judge_elapsed = time.time() - judge_start

        print(f"\n  Phase 2 complete: {len(verdicts)} judged ({judge_elapsed:.0f}s)")

    # ── Summary ──
    total_elapsed = conv_elapsed + judge_elapsed
    print(f"\n{'═' * 70}")
    print(f"  V2 TEST SUITE COMPLETE")
    print(f"{'═' * 70}")
    print(f"  Total tests:      {total}")
    print(f"  Conversations:    {conv_completed} completed, {conv_empty} empty/failed")
    print(f"  Total time:       {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")

    if verdicts:
        grade = compute_grade(verdicts)
        total_passed = grade["total_passed"]
        total_failed = grade["total_failed"]
        print(f"\n  ┌─────────────────────────────────────┐")
        print(f"  │  GRADE: {grade['letter_grade']:<4}  "
              f"SCORE: {grade['numeric_score']:.1f}/100       │")
        print(f"  │  PASSED: {total_passed}/{total}  "
              f"FAILED: {total_failed}/{total}             │")
        print(f"  └─────────────────────────────────────┘")

        if grade.get("breakdown_by_severity"):
            print(f"\n  By severity:")
            for sev in ["critical", "high", "medium", "low"]:
                if sev in grade["breakdown_by_severity"]:
                    bd = grade["breakdown_by_severity"][sev]
                    label = SEVERITY_LABELS.get(sev, sev)
                    print(f"    {label}: {bd['passed']}/{bd['total']} pass ({bd['pass_rate']})")

        if grade.get("critical_failures"):
            print(f"\n  Critical failures:")
            for cf in grade["critical_failures"]:
                print(f"    ❌ {cf}")

        # Print all failures with reasoning
        failures = [v for v in verdicts if not v.passed]
        if failures:
            print(f"\n{'─' * 70}")
            print(f"  FAILURES ({len(failures)}):")
            print(f"{'─' * 70}")
            for v in failures:
                sev = SEVERITY_LABELS.get(v.severity, v.severity)
                print(f"\n  {sev} {v.test_name}")
                print(f"  Reasoning: {v.reasoning}")
                if v.violations:
                    for viol in v.violations:
                        print(f"    • {viol}")

    print(f"\n{'═' * 70}")

    # ── Save results ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "suite": "v2_workflow_nodes",
        "version": "2.0",
        "timestamp": timestamp,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "elapsed_seconds": round(total_elapsed, 1),
        "runner_config": {
            "concurrency": args.concurrency,
            "stagger_rate": args.stagger_rate,
            "mode": "adaptive",
            "judge_enabled": not args.no_judge,
        },
        "summary": {
            "total_tests": total,
            "conversations_completed": conv_completed,
            "conversations_empty": conv_empty,
            "conv_elapsed_seconds": round(conv_elapsed, 1),
            "judge_elapsed_seconds": round(judge_elapsed, 1),
        },
        "results": [],
    }

    if verdicts:
        output["grade"] = compute_grade(verdicts)

    for i, (result, scenario) in enumerate(zip(results, scenarios)):
        entry = {
            **result.to_dict(),
            "_scenario": {
                "test_id": scenario["test_id"],
                "workflow_node": scenario["workflow_node"],
                "expected_path": scenario["expected_path"],
                "severity": scenario["severity"],
                "tags": scenario.get("tags", []),
                "v1_regression": scenario.get("v1_regression"),
                "pass_criteria": scenario["pass_criteria"],
                "ehr_context": scenario["ehr_context"],
                "expected_tools": scenario.get("expected_tools", []),
                "forbidden_phrases": scenario.get("forbidden_phrases", []),
            },
        }
        if i < len(verdicts):
            entry["_verdict"] = verdicts[i].to_dict()
        output["results"].append(entry)

    outpath = Path(RESULTS_DIR) / f"v2_parallel_{timestamp}.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {outpath}")

    # Save markdown report
    if verdicts:
        report_path = Path(RESULTS_DIR) / f"V2_REPORT_{timestamp}.md"
        _write_markdown_report(report_path, output, verdicts, scenarios, results)
        print(f"  Report saved: {report_path}")


def _write_markdown_report(path, output, verdicts, scenarios, results):
    """Generate a human-readable markdown report."""
    grade = output.get("grade", {})
    lines = [
        "# V2 STRESS TEST REPORT — Prime Psychiatry Voice Agent",
        f"## {output['summary']['total_tests']} Tests | "
        f"{output['date']} | Grade: {grade.get('letter_grade', 'N/A')}",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| **Tests Run** | {output['summary']['total_tests']} |",
        f"| **Conversations Completed** | {output['summary']['conversations_completed']} |",
        f"| **Grade** | **{grade.get('letter_grade', 'N/A')}** ({grade.get('numeric_score', 0)}/100) |",
        f"| **Pass Rate** | {grade.get('total_passed', 0)}/{grade.get('total_tests', 0)} |",
        f"| **Runtime** | {output['elapsed_seconds']:.0f}s |",
        "",
        "---",
        "",
        "## Results by Severity",
        "",
    ]

    for sev in ["critical", "high", "medium", "low"]:
        bd = grade.get("breakdown_by_severity", {}).get(sev)
        if bd:
            label = SEVERITY_LABELS.get(sev, sev)
            lines.append(f"### {label}: {bd['passed']}/{bd['total']} ({bd['pass_rate']})")
            lines.append("")
            sev_verdicts = [(v, s) for v, s in zip(verdicts, scenarios) if v.severity == sev]
            lines.append("| Test | Node | Verdict | Confidence |")
            lines.append("|------|------|---------|------------|")
            for v, s in sev_verdicts:
                status = "PASS" if v.passed else "**FAIL**"
                lines.append(f"| {v.test_name} | {s['workflow_node']} | {status} | {v.confidence}% |")
            lines.append("")

    # Failures section
    failures = [(v, s) for v, s in zip(verdicts, scenarios) if not v.passed]
    if failures:
        lines.append("---")
        lines.append("")
        lines.append(f"## Failures ({len(failures)})")
        lines.append("")
        for v, s in failures:
            label = SEVERITY_LABELS.get(v.severity, v.severity)
            lines.append(f"### {label} {v.test_name}")
            lines.append(f"**Node:** {s['workflow_node']}")
            lines.append(f"**Reasoning:** {v.reasoning}")
            if v.violations:
                lines.append("**Violations:**")
                for viol in v.violations:
                    lines.append(f"- {viol}")
            if v.mitigating_factors:
                lines.append("**Mitigating factors:**")
                for mf in v.mitigating_factors:
                    lines.append(f"- {mf}")
            lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
