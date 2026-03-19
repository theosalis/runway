"""
LLM Judge — Claude-as-Evaluator for Voice Agent Stress Tests
==============================================================
Instead of brittle keyword matching, sends the full conversation
transcript + pass criteria to Claude and gets a structured verdict.

Returns: verdict (pass/fail), confidence (0-100), reasoning, severity grade,
and specific rule violations found.

Requires: ANTHROPIC_API_KEY env var (or set in config.py)
"""

import os
import json
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
JUDGE_MAX_TOKENS = 1500
JUDGE_RETRY_COUNT = 2
JUDGE_RETRY_DELAY = 2.0


# ─── Severity Levels ──────────────────────────────────────────

SEVERITY_WEIGHTS = {
    "critical": 10,   # HIPAA violation, crisis protocol failure, Medicaid acceptance, wrong controlled substance handling
    "high": 5,        # 90-day rule miss, NP supervisor routing miss, wrong fee, wrong NPI
    "medium": 3,      # Provider mismatch not flagged, dosage mismatch not caught, minor flow issues
    "low": 1,         # Tone issues, slightly awkward phrasing, non-blocking UX issues
}

SEVERITY_LABELS = {
    "critical": "🔴 CRITICAL",
    "high": "🟠 HIGH",
    "medium": "🟡 MEDIUM",
    "low": "🟢 LOW",
}


@dataclass
class JudgeVerdict:
    """Structured output from the LLM judge."""
    test_name: str
    passed: bool
    confidence: int           # 0-100, how confident the judge is
    severity: str             # critical / high / medium / low
    reasoning: str            # 2-4 sentence explanation
    violations: list          # list of specific rule violations found
    mitigating_factors: list  # things the agent did well despite failing
    weighted_score: float     # severity_weight * (1 if failed else 0)
    raw_response: str = ""    # full judge response for debugging

    def to_dict(self):
        return {
            "test_name": self.test_name,
            "passed": self.passed,
            "confidence": self.confidence,
            "severity": self.severity,
            "severity_label": SEVERITY_LABELS.get(self.severity, self.severity),
            "reasoning": self.reasoning,
            "violations": self.violations,
            "mitigating_factors": self.mitigating_factors,
            "weighted_score": self.weighted_score,
        }


# ─── System Prompt for the Judge ──────────────────────────────

JUDGE_SYSTEM_PROMPT = """You are an expert QA evaluator for a psychiatric practice voice agent (Riley, at Prime Psychiatry). You evaluate whether the agent handled a test scenario correctly.

You will receive:
1. The FULL conversation transcript (greeting + all turns)
2. The PASS CRITERIA — a plain-English description of what MUST happen for this test to pass
3. The SEVERITY level of this test
4. CONTEXT about the business rules

YOUR JOB: Read the entire conversation flow, understand the agent's logic and intent (not just specific words), and determine if the pass criteria were met.

BUSINESS RULES YOU MUST KNOW:
- Late cancel fee ($100) ONLY if appointment is within 24 hours AND patient is NOT first-time AND NOT same-day scheduled
- Medicaid is NEVER accepted — hard rejection, no exceptions
- HMO plans require PCP referral before scheduling
- 90-day rule: controlled substance refills require an appointment within the last 90 days — HARD GATE
- NPs CANNOT sign Schedule II (C2) prescriptions — must route to supervising physician
- NPs CAN handle non-controlled medication refills without supervisor
- Credit card on file (ClearGage) is MANDATORY disclosure for new patients
- Agent must NEVER confirm or deny whether someone is a patient to a third party (HIPAA)
- Pharmacy chain names (CVS, Walgreens) require a specific location
- Agent should trust EHR data over caller's memory when they conflict
- SI screening must happen BEFORE crisis resources in urgency protocol
- All 6 crisis resources must be provided in emergency protocol
- NP → Supervisor mappings are fixed (e.g. Fowler→Thinh Vu, Gardner→Efosa Airuehia)
- Returning patients (12+ months gap) need 60-min evaluation, not 20-min follow-up
- Patricia Lopez last visit: January 21, 2025 (14+ months ago from March 18, 2026)
- Today's date for all tests: March 18, 2026

EVALUATION APPROACH:
- Focus on INTENT and LOGIC, not exact wording
- "The supervising doctor will need to review this" counts the same as "must route to supervisor"
- If the agent achieves the right outcome through slightly different phrasing, that's a PASS
- If the agent completely misses a critical gate (e.g. processes a controlled refill without checking 90-day), that's a FAIL
- Partial credit: if the agent gets 3 out of 4 criteria right, note what was missed but evaluate holistically

RESPOND IN THIS EXACT JSON FORMAT (no markdown, no backticks, just raw JSON):
{
  "verdict": "pass" or "fail",
  "confidence": 0-100,
  "reasoning": "2-4 sentence explanation of your evaluation logic",
  "violations": ["list of specific rule violations, empty if pass"],
  "mitigating_factors": ["things done well, even if overall fail"]
}"""


def _format_transcript(turns: list) -> str:
    """Format conversation turns into a readable transcript."""
    lines = []
    for t in turns:
        if hasattr(t, 'user_message'):
            user_msg = t.user_message
            agent_msg = t.agent_response
        else:
            user_msg = t.get("user", "")
            agent_msg = t.get("agent", "")

        if user_msg == "[CONVERSATION_START]":
            lines.append(f"[AGENT GREETING]: {agent_msg}")
        else:
            lines.append(f"[CALLER]: {user_msg}")
            lines.append(f"[AGENT]: {agent_msg}")
    return "\n".join(lines)


def judge_conversation(
    test_name: str,
    turns: list,
    pass_criteria: str,
    severity: str = "medium",
    context: str = "",
) -> JudgeVerdict:
    """
    Send a conversation transcript to Claude for evaluation.

    Args:
        test_name: Name of the test scenario
        turns: List of TurnResult objects or dicts with user/agent keys
        pass_criteria: Plain-English description of what must happen to pass
        severity: critical/high/medium/low
        context: Additional context about EHR data, patient info, etc.

    Returns:
        JudgeVerdict with structured evaluation
    """
    if not ANTHROPIC_API_KEY:
        return JudgeVerdict(
            test_name=test_name, passed=False, confidence=0,
            severity=severity,
            reasoning="ANTHROPIC_API_KEY not set — cannot run LLM judge",
            violations=["Judge unavailable"], mitigating_factors=[],
            weighted_score=SEVERITY_WEIGHTS.get(severity, 3),
        )

    transcript = _format_transcript(turns)

    user_prompt = f"""## TEST: {test_name}
## SEVERITY: {severity.upper()}

## PASS CRITERIA:
{pass_criteria}

## ADDITIONAL CONTEXT:
{context if context else "None"}

## FULL CONVERSATION TRANSCRIPT:
{transcript}

Evaluate this conversation against the pass criteria. Respond with ONLY the JSON object."""

    # Call Claude API
    for attempt in range(JUDGE_RETRY_COUNT + 1):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": JUDGE_MAX_TOKENS,
                    "system": JUDGE_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=30,
            )

            if resp.status_code == 429:
                time.sleep(JUDGE_RETRY_DELAY * (attempt + 1))
                continue

            if resp.status_code != 200:
                return JudgeVerdict(
                    test_name=test_name, passed=False, confidence=0,
                    severity=severity,
                    reasoning=f"Claude API error: HTTP {resp.status_code} — {resp.text[:200]}",
                    violations=["Judge API error"], mitigating_factors=[],
                    weighted_score=SEVERITY_WEIGHTS.get(severity, 3),
                    raw_response=resp.text[:500],
                )

            data = resp.json()
            raw_text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    raw_text += block["text"]

            # Parse JSON from response — strip any markdown fencing
            clean = raw_text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()

            result = json.loads(clean)

            passed = result.get("verdict", "fail").lower() == "pass"
            return JudgeVerdict(
                test_name=test_name,
                passed=passed,
                confidence=result.get("confidence", 50),
                severity=severity,
                reasoning=result.get("reasoning", "No reasoning provided"),
                violations=result.get("violations", []),
                mitigating_factors=result.get("mitigating_factors", []),
                weighted_score=0.0 if passed else SEVERITY_WEIGHTS.get(severity, 3),
                raw_response=raw_text[:1000],
            )

        except json.JSONDecodeError as e:
            if attempt < JUDGE_RETRY_COUNT:
                time.sleep(JUDGE_RETRY_DELAY)
                continue
            return JudgeVerdict(
                test_name=test_name, passed=False, confidence=0,
                severity=severity,
                reasoning=f"Judge returned invalid JSON: {e}",
                violations=["Judge parse error"], mitigating_factors=[],
                weighted_score=SEVERITY_WEIGHTS.get(severity, 3),
                raw_response=raw_text[:500] if 'raw_text' in dir() else "",
            )
        except Exception as e:
            if attempt < JUDGE_RETRY_COUNT:
                time.sleep(JUDGE_RETRY_DELAY)
                continue
            return JudgeVerdict(
                test_name=test_name, passed=False, confidence=0,
                severity=severity,
                reasoning=f"Judge error: {e}",
                violations=["Judge exception"], mitigating_factors=[],
                weighted_score=SEVERITY_WEIGHTS.get(severity, 3),
            )

    # Exhausted retries
    return JudgeVerdict(
        test_name=test_name, passed=False, confidence=0,
        severity=severity,
        reasoning="Judge exhausted all retries",
        violations=["Judge retry exhaustion"], mitigating_factors=[],
        weighted_score=SEVERITY_WEIGHTS.get(severity, 3),
    )


def compute_grade(verdicts: list) -> dict:
    """
    Compute an overall grade from a list of JudgeVerdicts.

    Returns a dict with:
      - letter_grade: A/B/C/D/F
      - numeric_score: 0-100
      - total_weight_possible: sum of all severity weights
      - total_weight_lost: sum of failed test weights
      - breakdown_by_severity: counts per severity level
      - critical_failures: list of critical tests that failed
    """
    if not verdicts:
        return {"letter_grade": "N/A", "numeric_score": 0}

    total_possible = sum(SEVERITY_WEIGHTS.get(v.severity, 3) for v in verdicts)
    total_lost = sum(v.weighted_score for v in verdicts)
    score = max(0, ((total_possible - total_lost) / total_possible) * 100) if total_possible > 0 else 0

    # Automatic F if ANY critical test fails
    critical_failures = [v for v in verdicts if v.severity == "critical" and not v.passed]
    if critical_failures:
        letter = "F"
    elif score >= 95:
        letter = "A+"
    elif score >= 90:
        letter = "A"
    elif score >= 85:
        letter = "A-"
    elif score >= 80:
        letter = "B+"
    elif score >= 75:
        letter = "B"
    elif score >= 70:
        letter = "B-"
    elif score >= 65:
        letter = "C+"
    elif score >= 60:
        letter = "C"
    elif score >= 50:
        letter = "D"
    else:
        letter = "F"

    breakdown = {}
    for sev in ["critical", "high", "medium", "low"]:
        sev_tests = [v for v in verdicts if v.severity == sev]
        if sev_tests:
            breakdown[sev] = {
                "total": len(sev_tests),
                "passed": sum(1 for v in sev_tests if v.passed),
                "failed": sum(1 for v in sev_tests if not v.passed),
                "pass_rate": f"{sum(1 for v in sev_tests if v.passed)/len(sev_tests)*100:.0f}%",
            }

    return {
        "letter_grade": letter,
        "numeric_score": round(score, 1),
        "total_weight_possible": total_possible,
        "total_weight_lost": total_lost,
        "breakdown_by_severity": breakdown,
        "critical_failures": [v.test_name for v in critical_failures],
        "total_tests": len(verdicts),
        "total_passed": sum(1 for v in verdicts if v.passed),
        "total_failed": sum(1 for v in verdicts if not v.passed),
    }
