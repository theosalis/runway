#!/usr/bin/env python3
"""
Parallel Conversation Runner — 100 Simultaneous Conversations
================================================================
Runs up to 100 conversations concurrently against the ElevenLabs agent.
Uses asyncio for non-blocking WebSocket connections.

Usage:
  export ELEVENLABS_API_KEY=your_key
  export WORKFLOW_1_AGENT_ID=your_agent_id

  python3 run_parallel.py                        # 120 tests, 100 concurrent
  python3 run_parallel.py --concurrency 50       # 50 concurrent
  python3 run_parallel.py --stagger-rate 5       # 5 new connections/sec
  python3 run_parallel.py --first 20             # First 20 tests
  python3 run_parallel.py --category A           # Category A only
  python3 run_parallel.py --mode adaptive        # Use LLM caller
  python3 run_parallel.py --dry-run              # Print plan
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
    DEFAULT_CONCURRENCY, DEFAULT_STAGGER_RATE,
    COMBINED_DEFAULT_CONCURRENCY,
)
from test_12_ehr_integration import ALL_SCENARIOS
from llm_judge import SEVERITY_LABELS
from parallel_runner import run_parallel_batch


def main():
    parser = argparse.ArgumentParser(description="Parallel Conversation Runner")
    parser.add_argument("--concurrency", type=int, default=None,
                        help=f"Max simultaneous conversations (default: {DEFAULT_CONCURRENCY} scripted, {COMBINED_DEFAULT_CONCURRENCY} adaptive)")
    parser.add_argument("--stagger-rate", type=float, default=DEFAULT_STAGGER_RATE,
                        help=f"Max new connections per second (default: {DEFAULT_STAGGER_RATE})")
    parser.add_argument("--mode", choices=["scripted", "adaptive"], default="scripted",
                        help="scripted=pre-written messages, adaptive=LLM caller")
    parser.add_argument("--first", type=int, help="Run only first N tests")
    parser.add_argument("--category", type=str, help="Run only one category (A-I)")
    parser.add_argument("--test", type=str, help="Run single test by name prefix")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    args = parser.parse_args()

    agent_id = WORKFLOW_1_AGENT_ID
    if not agent_id or "AGENT_ID" in agent_id:
        print("ERROR: Set WORKFLOW_1_AGENT_ID environment variable.")
        sys.exit(1)

    if args.mode == "adaptive" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY for adaptive mode.")
        sys.exit(1)

    concurrency = args.concurrency
    if concurrency is None:
        concurrency = (
            COMBINED_DEFAULT_CONCURRENCY
            if args.mode == "adaptive"
            else DEFAULT_CONCURRENCY
        )

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
    print(f"PARALLEL CONVERSATION RUNNER — {concurrency} CONCURRENT")
    print(f"Prime Psychiatry Voice Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"\nAgent:       {agent_id[:16]}...")
    print(f"Tests:       {total}")
    print(f"Concurrency: {concurrency}")
    print(f"Stagger:     {args.stagger_rate} connections/sec")
    print(f"Mode:        {args.mode}")
    print(f"Severity:    {sevs.get('critical',0)} critical, {sevs.get('high',0)} high, "
          f"{sevs.get('medium',0)} medium, {sevs.get('low',0)} low")
    est_time = total / args.stagger_rate + 30
    print(f"Est. time:   ~{est_time:.0f}s ({est_time/60:.1f} min)")
    print()

    if args.dry_run:
        for s in scenarios:
            sev = SEVERITY_LABELS.get(s["severity"], s["severity"])
            print(f"  {sev} {s['test_name']} ({len(s['messages'])} turns)")
        print(f"\n[DRY RUN — no API calls made]")
        print(f"Would run {total} tests at {concurrency} concurrent, "
              f"{args.stagger_rate} conn/sec")
        return

    completed_lock = asyncio.Lock if hasattr(asyncio, 'Lock') else None
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
        concurrency=concurrency,
        stagger_rate=args.stagger_rate,
        mode=args.mode,
        progress_callback=progress,
    ))

    print(f"\n{'═' * 70}")
    print(f"  PARALLEL RUN COMPLETE")
    print(f"  {batch_result.total_tests} tests | "
          f"{batch_result.completed} completed | "
          f"{batch_result.failed} failed | "
          f"{batch_result.errors} errors")
    print(f"  Elapsed: {batch_result.elapsed_seconds:.1f}s "
          f"({batch_result.elapsed_seconds/60:.1f} min)")
    print(f"  Concurrency: {concurrency} | Mode: {args.mode}")
    print(f"{'═' * 70}")

    if batch_result.error_details:
        print(f"\n  ERRORS:")
        for err in batch_result.error_details[:10]:
            print(f"    • {err.get('test', '?')}: {err.get('error', '?')[:100]}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "suite": "12_ehr_integration",
        "mode": f"parallel_{args.mode}",
        "timestamp": timestamp,
        "elapsed_seconds": batch_result.elapsed_seconds,
        "runner_config": {
            "concurrency": concurrency,
            "stagger_rate": args.stagger_rate,
            "mode": args.mode,
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
                    "mode": args.mode,
                },
            }
            for r, s in zip(batch_result.results, scenarios)
        ],
        "error_details": batch_result.error_details,
    }

    outpath = Path(RESULTS_DIR) / f"suite12_parallel_{timestamp}.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {outpath}")


if __name__ == "__main__":
    main()
