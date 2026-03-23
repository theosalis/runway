#!/usr/bin/env python3
"""
Combined Runner — Adaptive + Parallel (Full Power Mode)
=========================================================
Runs LLM-powered adaptive conversations in parallel.
Each concurrent conversation has its own Claude Haiku caller agent.

Usage:
  export ELEVENLABS_API_KEY=your_key
  export WORKFLOW_1_AGENT_ID=your_agent_id
  export ANTHROPIC_API_KEY=your_key

  python3 run_combined.py                        # 120 adaptive, 50 concurrent
  python3 run_combined.py --concurrency 20       # 20 concurrent
  python3 run_combined.py --first 10             # First 10 tests
  python3 run_combined.py --category A           # Category A only
  python3 run_combined.py --dry-run              # Print plan

Cost: ~$0.72 per full 120-test run (Haiku caller) + ElevenLabs usage
"""

import sys
import os
import json
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from collections import Counter

from config import (
    WORKFLOW_1_AGENT_ID, RESULTS_DIR,
    COMBINED_DEFAULT_CONCURRENCY, DEFAULT_STAGGER_RATE,
)
from test_12_ehr_integration import ALL_SCENARIOS
from llm_judge import SEVERITY_LABELS
from caller_agent import scenario_to_persona
from parallel_runner import run_parallel_batch


def main():
    parser = argparse.ArgumentParser(
        description="Combined: Adaptive LLM Caller + Parallel Execution"
    )
    parser.add_argument("--concurrency", type=int, default=COMBINED_DEFAULT_CONCURRENCY,
                        help=f"Max concurrent conversations (default: {COMBINED_DEFAULT_CONCURRENCY})")
    parser.add_argument("--stagger-rate", type=float, default=5.0,
                        help="Max new connections per second (default: 5)")
    parser.add_argument("--first", type=int, help="Run only first N tests")
    parser.add_argument("--category", type=str, help="Run only one category (A-I)")
    parser.add_argument("--test", type=str, help="Run single test by name prefix")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    args = parser.parse_args()

    agent_id = WORKFLOW_1_AGENT_ID
    if not agent_id or "AGENT_ID" in agent_id:
        print("ERROR: Set WORKFLOW_1_AGENT_ID environment variable.")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
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
    est_haiku_cost = total * 10 * 0.0006
    est_time = total / args.stagger_rate + 60

    print("=" * 70)
    print(f"COMBINED RUNNER — ADAPTIVE + PARALLEL ({args.concurrency} CONCURRENT)")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"\nAgent:       {agent_id[:16]}...")
    print(f"Tests:       {total}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Stagger:     {args.stagger_rate} connections/sec")
    print(f"Mode:        ADAPTIVE (Claude Haiku caller)")
    print(f"Severity:    {sevs.get('critical',0)} critical, {sevs.get('high',0)} high, "
          f"{sevs.get('medium',0)} medium, {sevs.get('low',0)} low")
    print(f"Est. cost:   ~${est_haiku_cost:.2f} (Haiku caller)")
    print(f"Est. time:   ~{est_time:.0f}s ({est_time/60:.1f} min)")
    print()

    if args.dry_run:
        for s in scenarios:
            sev = SEVERITY_LABELS.get(s["severity"], s["severity"])
            persona = scenario_to_persona(s)
            print(f"  {sev} {s['test_name']}")
            print(f"       → {persona.name}: {persona.goal}")
        print(f"\n[DRY RUN — no API calls made]")
        print(f"Would run {total} adaptive conversations at {args.concurrency} concurrent")
        return

    pass_count = [0]
    fail_count = [0]

    def progress(completed, total_count, result):
        status = "✅" if result.passed and result.turns else "❌"
        turns = len(result.turns)
        avg_ms = result.avg_latency_ms
        if result.passed and result.turns:
            pass_count[0] += 1
        else:
            fail_count[0] += 1
        pct = completed / total_count * 100
        print(f"  [{completed:>3}/{total_count}] {pct:>5.1f}% {status} {result.test_name:<50} "
              f"{turns:>2} turns  {avg_ms:>6.0f}ms  "
              f"(pass:{pass_count[0]} fail:{fail_count[0]})")

    batch_result = asyncio.run(run_parallel_batch(
        agent_id=agent_id,
        workflow_label="workflow_1",
        scenarios=scenarios,
        concurrency=args.concurrency,
        stagger_rate=args.stagger_rate,
        mode="adaptive",
        progress_callback=progress,
    ))

    print(f"\n{'═' * 70}")
    print(f"  COMBINED RUN COMPLETE (Adaptive + Parallel)")
    print(f"  {batch_result.total_tests} tests | "
          f"{batch_result.completed} completed | "
          f"{batch_result.failed} failed | "
          f"{batch_result.errors} errors")
    print(f"  Elapsed: {batch_result.elapsed_seconds:.1f}s "
          f"({batch_result.elapsed_seconds/60:.1f} min)")
    print(f"  vs sequential: ~{total * 180}s ({total * 3:.0f} min) — "
          f"{(total * 180) / max(batch_result.elapsed_seconds, 1):.0f}x faster")
    print(f"{'═' * 70}")

    if batch_result.error_details:
        print(f"\n  ERRORS:")
        for err in batch_result.error_details[:10]:
            print(f"    • {err.get('test', '?')}: {err.get('error', '?')[:100]}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "suite": "12_ehr_integration",
        "mode": "combined_adaptive_parallel",
        "timestamp": timestamp,
        "elapsed_seconds": batch_result.elapsed_seconds,
        "runner_config": {
            "concurrency": args.concurrency,
            "stagger_rate": args.stagger_rate,
            "mode": "adaptive",
            "caller_model": "claude-haiku-4-20250514",
        },
        "summary": {
            "total_tests": batch_result.total_tests,
            "completed": batch_result.completed,
            "failed": batch_result.failed,
            "errors": batch_result.errors,
        },
        "results": [
            {
                **r.to_dict(),
                "_test_metadata": {
                    "pass_criteria": s["pass_criteria"],
                    "severity": s["severity"],
                    "context": s.get("context", ""),
                    "mode": "adaptive",
                },
            }
            for r, s in zip(batch_result.results, scenarios)
        ],
        "error_details": batch_result.error_details,
    }

    outpath = Path(RESULTS_DIR) / f"suite12_combined_{timestamp}.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {outpath}")


if __name__ == "__main__":
    main()
