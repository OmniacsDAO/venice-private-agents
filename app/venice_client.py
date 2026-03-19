"""
Venice AI client — privacy-preserving inference.

Venice provides no-data-retention inference: prompts and completions are
processed in real-time and never stored, logged, or used for training.
This is the core privacy guarantee that makes Veiled Oracle possible.

The client uses Venice's OpenAI-compatible API, so any OpenAI SDK works
with a base_url swap.
"""

import asyncio
import json
import os
from typing import Optional

from openai import OpenAI


def get_venice_client() -> OpenAI:
    """Create a Venice-connected OpenAI client."""
    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        raise RuntimeError("VENICE_API_KEY must be set")
    return OpenAI(api_key=api_key, base_url="https://api.venice.ai/api/v1")


SYSTEM_PROMPT_TREASURY = """\
You are a confidential treasury analyst. You analyze on-chain treasury data
and produce structured assessments. Your analysis is private — the raw data
and your reasoning are never stored or logged (Venice no-data-retention).

Your output will be split into two parts:
1. A PUBLIC VERDICT: A single severity level (healthy/caution/warning/critical)
   and a one-sentence summary. This gets published on-chain. It must contain
   NO sensitive details — only the conclusion.
2. A PRIVATE REPORT: A detailed analysis with findings, risks, and
   recommendations. This gets stored on x402-pastebin for the requester.

Always respond in this exact JSON format:
{
  "severity": "healthy|caution|warning|critical",
  "verdict_summary": "One sentence public verdict with no sensitive data",
  "report": {
    "overview": "2-3 sentence overview",
    "holdings_analysis": "Analysis of token holdings and concentrations",
    "risk_factors": ["risk1", "risk2", ...],
    "recommendations": ["rec1", "rec2", ...],
    "confidence": "high|medium|low"
  }
}
"""

SYSTEM_PROMPT_GOVERNANCE = """\
You are a confidential governance analyst. You analyze DAO governance activity
— proposals, voting patterns, delegate behavior — and produce structured
assessments. Your analysis is private (Venice no-data-retention).

Output format:
{
  "severity": "healthy|caution|warning|critical",
  "verdict_summary": "One sentence public verdict with no sensitive data",
  "report": {
    "overview": "2-3 sentence overview",
    "participation_analysis": "Voter turnout and engagement patterns",
    "centralization_risks": "Power concentration among delegates",
    "notable_patterns": ["pattern1", "pattern2", ...],
    "recommendations": ["rec1", "rec2", ...],
    "confidence": "high|medium|low"
  }
}
"""

SYSTEM_PROMPT_RISK = """\
You are a confidential risk assessment agent. You analyze protocol and smart
contract risk factors — TVL changes, audit status, dependency chains,
liquidity depth — and produce structured risk assessments.
Your analysis is private (Venice no-data-retention).

Output format:
{
  "severity": "healthy|caution|warning|critical",
  "verdict_summary": "One sentence public verdict with no sensitive data",
  "report": {
    "overview": "2-3 sentence overview",
    "risk_matrix": "Assessment of key risk categories",
    "exposure_analysis": "Where the biggest exposures lie",
    "risk_factors": ["risk1", "risk2", ...],
    "mitigations": ["mitigation1", "mitigation2", ...],
    "confidence": "high|medium|low"
  }
}
"""

SYSTEM_PROMPT_DUE_DILIGENCE = """\
You are a confidential due diligence agent. You research projects, teams,
and protocols to produce trust assessments. Your analysis is private
(Venice no-data-retention).

Output format:
{
  "severity": "healthy|caution|warning|critical",
  "verdict_summary": "One sentence public verdict with no sensitive data",
  "report": {
    "overview": "2-3 sentence overview",
    "legitimacy_signals": "Positive indicators of legitimacy",
    "red_flags": ["flag1", "flag2", ...],
    "recommendations": ["rec1", "rec2", ...],
    "confidence": "high|medium|low"
  }
}
"""

SYSTEM_PROMPTS = {
    "treasury": SYSTEM_PROMPT_TREASURY,
    "governance": SYSTEM_PROMPT_GOVERNANCE,
    "risk": SYSTEM_PROMPT_RISK,
    "due_diligence": SYSTEM_PROMPT_DUE_DILIGENCE,
}


async def run_private_analysis(
    analysis_type: str,
    target: str,
    on_chain_data: dict,
    private_context: Optional[str] = None,
) -> dict:
    """
    Run a private analysis via Venice AI.

    Privacy guarantees:
    - Venice does not retain prompts or completions
    - The raw on-chain data and private context are sent only to Venice
    - No intermediate storage occurs — data flows in, analysis flows out
    - The returned dict is split into verdict (public) and report (private)
    """
    client = get_venice_client()
    model = os.getenv("VENICE_MODEL", "qwen3-235b-a22b-instruct-2507")
    system_prompt = SYSTEM_PROMPTS.get(analysis_type, SYSTEM_PROMPT_TREASURY)

    user_message = f"Analyze the following target: {target}\n\n"
    user_message += f"On-chain data:\n{_format_chain_data(on_chain_data)}\n"
    if private_context:
        user_message += (
            f"\nAdditional private context (confidential):\n{private_context}\n"
        )

    # Venice no-data-retention inference — this is where privacy happens
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    raw = response.choices[0].message.content

    # Parse the JSON response
    # Handle thinking tags or markdown code blocks
    text = raw
    if "</think>" in text:
        text = text.split("</think>")[-1]
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract what we can
        result = {
            "severity": "caution",
            "verdict_summary": f"Analysis of {target} completed — review full report for details.",
            "report": {
                "overview": text[:500],
                "risk_factors": [],
                "recommendations": ["Review the full analysis output"],
                "confidence": "low",
            },
        }

    return result


def _format_chain_data(data: dict) -> str:
    """Format on-chain data for the LLM prompt."""
    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for k, v in value.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
