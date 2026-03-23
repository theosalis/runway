"""
Parallel Conversation Runner
==============================
Runs up to N conversations concurrently using asyncio.
Supports pre-written messages (scripted) and LLM-powered caller (adaptive).
"""

import asyncio
import json
import time
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from client import ConversationResult
from async_client import async_run_conversation_test
from caller_agent import scenario_to_persona
from config import (
    ELEVENLABS_API_KEY,
    WORKFLOW_1_AGENT_ID,
    RESULTS_DIR,
    DEFAULT_CONCURRENCY,
    DEFAULT_STAGGER_RATE,
)


@dataclass
class ParallelBatchResult:
    """Results from a parallel batch run."""
    total_tests: int
    completed: int
    failed: int
    errors: int
    elapsed_seconds: float
    concurrency: int
    mode: str
    results: list
    error_details: list = field(default_factory=list)

    def to_dict(self):
        return {
            "total_tests": self.total_tests,
            "completed": self.completed,
            "failed": self.failed,
            "errors": self.errors,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "concurrency": self.concurrency,
            "mode": self.mode,
            "results": [r.to_dict() for r in self.results],
            "error_details": self.error_details,
        }


async def run_parallel_batch(
    agent_id: str,
    workflow_label: str,
    scenarios: list,
    concurrency: int = DEFAULT_CONCURRENCY,
    stagger_rate: float = DEFAULT_STAGGER_RATE,
    mode: str = "scripted",
    progress_callback: Optional[Callable] = None,
) -> ParallelBatchResult:
    """
    Run all scenarios in parallel with concurrency limiting.

    Args:
        agent_id: ElevenLabs agent ID
        workflow_label: Label for results
        scenarios: List of test scenario dicts
        concurrency: Max simultaneous conversations
        stagger_rate: Max new connections per second
        mode: "scripted" or "adaptive"
        progress_callback: Called with (completed, total, result)
    """
    semaphore = asyncio.Semaphore(concurrency)
    total = len(scenarios)
    completed_count = 0
    errors = []
    lock = asyncio.Lock()

    async def run_one(
        scenario: dict,
        index: int,
        session: aiohttp.ClientSession,
    ) -> ConversationResult:
        nonlocal completed_count

        initial_delay = index / stagger_rate
        await asyncio.sleep(initial_delay)

        try:
            if mode == "adaptive":
                persona = scenario_to_persona(scenario)
                result = await async_run_conversation_test(
                    agent_id=agent_id,
                    workflow_label=workflow_label,
                    test_name=scenario["test_name"],
                    persona=persona,
                    expected_nodes=scenario.get("expected_nodes"),
                    session=session,
                    semaphore=semaphore,
                )
            else:
                result = await async_run_conversation_test(
                    agent_id=agent_id,
                    workflow_label=workflow_label,
                    test_name=scenario["test_name"],
                    messages=scenario["messages"],
                    expected_nodes=scenario.get("expected_nodes"),
                    session=session,
                    semaphore=semaphore,
                )
        except Exception as e:
            result = ConversationResult(
                test_name=scenario["test_name"],
                agent_id=agent_id,
                workflow_label=workflow_label,
                turns=[],
                total_duration_ms=0,
                passed=False,
                failure_reason=f"Exception: {e}",
            )
            async with lock:
                errors.append({
                    "test": scenario["test_name"],
                    "error": str(e),
                })

        async with lock:
            completed_count += 1
            current = completed_count

        if progress_callback:
            progress_callback(current, total, result)

        return result

    connector = aiohttp.TCPConnector(limit=concurrency + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            run_one(s, i, session) for i, s in enumerate(scenarios)
        ]
        start = time.time()
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start

    clean_results = []
    for r in raw_results:
        if isinstance(r, Exception):
            errors.append({"error": str(r)})
            clean_results.append(ConversationResult(
                test_name="unknown",
                agent_id=agent_id,
                workflow_label=workflow_label,
                turns=[],
                total_duration_ms=0,
                passed=False,
                failure_reason=str(r),
            ))
        else:
            clean_results.append(r)

    return ParallelBatchResult(
        total_tests=total,
        completed=sum(1 for r in clean_results if r.turns),
        failed=sum(1 for r in clean_results if not r.passed),
        errors=len(errors),
        elapsed_seconds=elapsed,
        concurrency=concurrency,
        mode=mode,
        results=clean_results,
        error_details=errors,
    )
