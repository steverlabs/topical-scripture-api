"""Classifies user topics into taxonomy categories using Claude."""

import json
import os

import anthropic
from dotenv import load_dotenv

from taxonomy import load_taxonomy

load_dotenv()

_client: anthropic.Anthropic | None = None
_system_prompt: str | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _get_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is not None:
        return _system_prompt

    topics = load_taxonomy()["topics"]
    lines = []
    for t in topics:
        examples = " | ".join(t["intent_examples"])
        lines.append(f'- id: "{t["id"]}", name: "{t["name"]}", examples: [{examples}]')

    _system_prompt = (
        "You are a theological topic classifier for a pastoral scripture API.\n\n"
        "Given a user's message, identify which of the following topics it relates to.\n\n"
        "Available topics:\n"
        + "\n".join(lines)
        + """

Rules:
- Return ONLY a JSON array of matching topic IDs, ordered by relevance (most relevant first).
- Maximum 3 IDs. Use only IDs from the list above — never invent new ones.
- If no topic fits, return an empty array: []
- Fewer matches imply higher specificity. Only include topics that genuinely fit.

Examples:
  "I can't stop worrying about my job"      → ["anxiety"]
  "My mother died and I feel lost"          → ["grief"]
  "I'm not sure I believe in God anymore"   → ["doubt"]
  "I feel anxious and question my faith"    → ["anxiety", "doubt"]
  "What's the weather today?"               → []

Respond with ONLY the JSON array. No explanation, no markdown, no other text."""
    )
    return _system_prompt


def classify_intent(user_input: str) -> list:
    """Return a list of taxonomy topic IDs matching the user input.

    Results are ordered by relevance, capped at 3. Fewer results indicate
    higher specificity — a single match is a stronger signal than three.
    Returns an empty list if nothing matches or on any error.
    """
    try:
        response = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": _get_system_prompt(),
                    # Cache the stable taxonomy prompt across requests.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_input}],
        )

        text = next(
            (b.text for b in response.content if b.type == "text"), ""
        ).strip()

        result = json.loads(text)
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, str)][:3]

    except Exception:
        return []
