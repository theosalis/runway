"""
ElevenLabs Conversational AI Stress Test — Configuration
=========================================================
Prime Psychiatry Voice Agent — Full Node Coverage

Setup:
  1. Set your ElevenLabs API key as env var: export ELEVENLABS_API_KEY=your_key
  2. Set your agent IDs:
     export WORKFLOW_1_AGENT_ID=your_workflow_1_agent_id
     export WORKFLOW_2_AGENT_ID=your_workflow_2_agent_id
  3. pip install requests websockets
  4. Run: python run_all_tests.py
"""

import os

# ─── API Configuration ────────────────────────────────────────────────
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "YOUR_API_KEY_HERE")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"

# Agent IDs for each workflow variant
WORKFLOW_1_AGENT_ID = os.environ.get("WORKFLOW_1_AGENT_ID", "AGENT_ID_WF1")
WORKFLOW_2_AGENT_ID = os.environ.get("WORKFLOW_2_AGENT_ID", "AGENT_ID_WF2")

# ─── Test Configuration ──────────────────────────────────────────────
# Max seconds to wait for agent response per turn
TURN_TIMEOUT_SECONDS = 30

# Max turns per conversation before force-ending
MAX_TURNS_PER_CONVERSATION = 40

# Delay between API calls to avoid rate limiting (seconds)
INTER_CALL_DELAY = 1.0

# Output directory for results
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)
