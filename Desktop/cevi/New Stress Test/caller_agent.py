"""
Caller Agent — LLM-Powered Patient Simulator
==============================================
Uses Claude Haiku to generate realistic patient responses in real-time
based on what the ElevenLabs agent actually says.

Each test scenario is converted into a CallerPersona, then Claude role-plays
as that patient during the live WebSocket conversation.
"""

import os
import re
import json
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CALLER_MODEL = os.environ.get("CALLER_MODEL", "claude-haiku-4-5-20251001")
CALLER_MAX_TOKENS = 300
CALLER_RETRY_COUNT = 2
CALLER_RETRY_DELAY = 1.0


@dataclass
class CallerPersona:
    """Describes who the simulated caller is and how they should behave."""
    name: str
    goal: str
    medical_details: str
    behavior_notes: str
    exit_conditions: list
    max_turns: int = 15
    deliberate_errors: list = field(default_factory=list)


@dataclass
class CallerResponse:
    """What the caller says next + metadata."""
    message: str
    should_end_call: bool = False
    reasoning: str = ""
    generation_latency_ms: float = 0.0


CALLER_SYSTEM_PROMPT = """You are simulating a phone call to Prime Psychiatry. You are role-playing as a patient (or caller) with specific details. Respond naturally and conversationally as a real person would on the phone.

YOUR IDENTITY:
- Name: {name}
- Goal: {goal}
- Your medical details (use ONLY when asked): {medical_details}
- Behavior: {behavior_notes}

{deliberate_errors_section}

RULES:
1. Respond to what the agent ACTUALLY says. If they ask a question, answer it naturally.
2. Keep responses SHORT — 1-2 sentences max. Real phone callers don't give speeches.
3. Provide your personal details (name, DOB, medication, provider, pharmacy) ONLY when the agent asks for them. Don't volunteer everything at once.
4. Sound natural — brief, conversational. Say "yeah" or "uh huh" sometimes instead of formal language.
5. If the agent asks you to confirm something that matches your details, confirm it. If it doesn't match, correct it.
6. NEVER break character. You ARE this person calling a doctor's office.
7. If the agent seems stuck or keeps asking the same thing, try rephrasing or giving more context.
8. When your goal is complete (refill submitted, appointment scheduled, question answered), wrap up naturally: "Thanks, that's all I needed" or similar.

EXIT CONDITIONS — Set should_end to true when ANY of these happen:
{exit_conditions}
- The agent says goodbye, thanks you for calling, or asks "anything else?" and your goal is done
- You've said everything you can and the conversation has reached a natural end
- The agent has clearly completed your request

RESPOND WITH ONLY THIS JSON (no markdown, no backticks):
{{"message": "your response as the caller", "should_end": false, "reasoning": "brief note about why you said this"}}"""


def _build_system_prompt(persona: CallerPersona) -> str:
    """Build the system prompt for the caller agent."""
    errors_section = ""
    if persona.deliberate_errors:
        errors_section = "DELIBERATE ERRORS TO MAKE:\n"
        for err in persona.deliberate_errors:
            errors_section += f"- {err}\n"
        errors_section += "Make these errors naturally, and correct yourself only when the agent pushes back or you 'realize' the mistake.\n"

    exit_lines = "\n".join(f"- {c}" for c in persona.exit_conditions)

    return CALLER_SYSTEM_PROMPT.format(
        name=persona.name,
        goal=persona.goal,
        medical_details=persona.medical_details,
        behavior_notes=persona.behavior_notes,
        deliberate_errors_section=errors_section,
        exit_conditions=exit_lines,
    )


def _format_history(conversation_history: list) -> list:
    """Convert conversation history to Anthropic messages format."""
    messages = []
    for entry in conversation_history:
        role = entry["role"]
        text = entry["text"]
        if not text:
            continue
        if role == "agent":
            messages.append({"role": "user", "content": f"[AGENT]: {text}"})
        elif role == "caller":
            messages.append({"role": "assistant", "content": text})
    return messages


def generate_caller_response(
    persona: CallerPersona,
    conversation_history: list,
    turn_index: int,
) -> CallerResponse:
    """
    Generate the next caller message based on conversation history.
    Uses Claude Haiku for low latency.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or ANTHROPIC_API_KEY
    if not api_key:
        print(f"    ⚠️  ANTHROPIC_API_KEY not set! Using fallback response.", flush=True)
        return CallerResponse(
            message="I need to speak with someone about my medication.",
            reasoning="ANTHROPIC_API_KEY not set, using fallback",
        )

    system_prompt = _build_system_prompt(persona)
    messages = _format_history(conversation_history)

    if not messages:
        messages = [{"role": "user", "content": "[AGENT]: Thank you for calling Prime Psychiatry. How can I help you?"}]

    if messages[-1]["role"] != "user":
        return CallerResponse(
            message="Yes.",
            reasoning="Last message wasn't from agent, sending filler",
        )

    start_time = time.perf_counter()

    for attempt in range(CALLER_RETRY_COUNT + 1):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CALLER_MODEL,
                    "max_tokens": CALLER_MAX_TOKENS,
                    "system": system_prompt,
                    "messages": messages,
                },
                timeout=15,
            )

            if resp.status_code == 429:
                time.sleep(CALLER_RETRY_DELAY * (attempt + 1))
                continue

            if resp.status_code != 200:
                print(f"    ⚠️  Caller API error {resp.status_code}: {resp.text[:150]}", flush=True)
                return CallerResponse(
                    message="Can you repeat that?",
                    reasoning=f"API error {resp.status_code}: {resp.text[:200]}",
                    generation_latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            data = resp.json()
            raw_text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    raw_text += block["text"]

            clean = raw_text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()

            result = json.loads(clean)
            latency = (time.perf_counter() - start_time) * 1000

            return CallerResponse(
                message=result.get("message", "Yes."),
                should_end_call=result.get("should_end", False),
                reasoning=result.get("reasoning", ""),
                generation_latency_ms=latency,
            )

        except json.JSONDecodeError:
            if attempt < CALLER_RETRY_COUNT:
                time.sleep(CALLER_RETRY_DELAY)
                continue
            latency = (time.perf_counter() - start_time) * 1000
            return CallerResponse(
                message=raw_text[:200] if raw_text else "Yes.",
                reasoning="JSON parse failed, using raw text",
                generation_latency_ms=latency,
            )
        except Exception as e:
            if attempt < CALLER_RETRY_COUNT:
                time.sleep(CALLER_RETRY_DELAY)
                continue
            latency = (time.perf_counter() - start_time) * 1000
            return CallerResponse(
                message="Can you repeat that please?",
                reasoning=f"Exception: {e}",
                generation_latency_ms=latency,
            )

    latency = (time.perf_counter() - start_time) * 1000
    return CallerResponse(
        message="Sorry, can you say that again?",
        reasoning="Exhausted retries",
        generation_latency_ms=latency,
    )


def scenario_to_persona(scenario: dict) -> CallerPersona:
    """Convert an existing test scenario dict into a CallerPersona."""
    test_name = scenario["test_name"]
    messages = scenario["messages"]
    context = scenario.get("context", "")
    pass_criteria = scenario["pass_criteria"]

    name = _extract_name(context, messages, test_name)
    goal = messages[0] if messages else "I need help with my medication."

    behavior = "Cooperative and provides information when asked."
    if "wrong" in test_name or "lies" in test_name:
        behavior = "Initially provides incorrect information, but corrects when pushed."
    elif "hipaa" in test_name:
        behavior = "Third-party caller asking about someone else. Persistent but eventually accepts refusal."
    elif "fake" in test_name or "unknown" in test_name:
        behavior = "Genuinely believes they are a patient. Confused when told not found."
    elif "minor" in test_name:
        behavior = "Parent calling on behalf of minor child. Cooperative."

    deliberate_errors = _detect_deliberate_errors(messages, context)

    exit_conditions = [
        "Agent confirms your request has been submitted or completed",
        "Agent says goodbye or asks if there's anything else (and your goal is met)",
        "Conversation has naturally concluded",
    ]
    if "refill" in goal.lower():
        exit_conditions.insert(0, "Refill request has been submitted")
    elif "schedule" in goal.lower() or "appointment" in goal.lower():
        exit_conditions.insert(0, "Appointment has been scheduled or scheduling info taken")
    elif "npi" in test_name.lower():
        exit_conditions.insert(0, "NPI number has been provided")

    return CallerPersona(
        name=name,
        goal=goal,
        medical_details=context,
        behavior_notes=behavior,
        exit_conditions=exit_conditions,
        deliberate_errors=deliberate_errors,
    )


def _extract_name(context: str, messages: list, test_name: str) -> str:
    """Extract patient name from context, messages, or test name."""
    match = re.search(r"EHR:\s*([A-Z][a-z]+ [A-Z][a-z\-]+)", context)
    if match:
        return match.group(1)

    for msg in messages:
        name_match = re.search(
            r"([A-Z][a-z]+ [A-Z][a-z\-]+)(?:,|\s+(?:DOB|date of birth|D\.O\.B))",
            msg,
        )
        if name_match:
            return name_match.group(1)

    parts = test_name.split("_")
    name_parts = []
    for p in parts[1:]:
        if p[0].isupper() or (len(p) > 1 and p.isalpha()):
            name_parts.append(p.capitalize())
        if len(name_parts) >= 2:
            break

    return " ".join(name_parts) if name_parts else "The Caller"


def _detect_deliberate_errors(messages: list, context: str) -> list:
    """Detect intentional errors in message flow by comparing to context."""
    errors = []

    dob_matches = re.findall(
        r"(?:DOB|date of birth)[:\s]+([A-Z][a-z]+ \d{1,2},?\s*\d{4})",
        context,
        re.IGNORECASE,
    )
    if dob_matches:
        correct_dob = dob_matches[0]
        for msg in messages:
            msg_dobs = re.findall(
                r"(?:DOB|date of birth)[:\s]+([A-Z][a-z]+ \d{1,2},?\s*\d{4})",
                msg,
                re.IGNORECASE,
            )
            for msg_dob in msg_dobs:
                if msg_dob != correct_dob and correct_dob[:3] in msg_dob:
                    errors.append(
                        f"Initially give wrong DOB '{msg_dob}', "
                        f"then correct to '{correct_dob}' when agent can't find you"
                    )

    if "NOT" in context:
        provider_match = re.search(r"NOT\s+([A-Za-z\s]+?)[\.\)]", context)
        if provider_match:
            wrong_provider = provider_match.group(1).strip()
            errors.append(
                f"Initially say your provider is {wrong_provider}, "
                f"then accept correction when agent flags it"
            )

    return errors
