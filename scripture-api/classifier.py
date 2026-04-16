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
    topic_blocks = []

    for t in topics:
        examples = " | ".join(t["intent_examples"])
        lines = [f'Topic id="{t["id"]}" name="{t["name"]}"']
        lines.append(f'  General intent examples: {examples}')

        for v in t.get("topic_variants", []):
            signals = " | ".join(v["intent_signals"])
            lines.append(f'  Variant id="{v["id"]}" label="{v["label"]}"')
            lines.append(f'    Description: {v["description"]}')
            lines.append(f'    Intent signals: {signals}')

        topic_blocks.append("\n".join(lines))

    topics_str = "\n\n".join(topic_blocks)

    _system_prompt = f"""\
You are a theological topic classifier for a pastoral scripture API.

Given a user's message, identify which topics it relates to and, when the signals \
are clear, which variant within that topic best describes their situation.

Available topics and variants:

{topics_str}

Rules:
- Return ONLY a JSON array of classification objects, ordered by relevance (most relevant first).
- Maximum 3 objects. Use only topic IDs and variant IDs from the lists above — never invent new ones.
- If no topic fits, return an empty array: []
- Set "variant_id" to the most fitting variant ID when the user's input clearly signals one. \
Set it to null when the variant is ambiguous or no variant fits better than the general topic.
- Fewer matches imply higher specificity. Only include topics that genuinely fit.

Output format — each object must have exactly these two keys:
  "topic_id": string
  "variant_id": string or null

Examples:
  "I can't stop worrying about losing my job"
    → [{{"topic_id": "anxiety", "variant_id": "circumstantial_anxiety"}}]

  "I'm filled with dread and I don't even know why"
    → [{{"topic_id": "anxiety", "variant_id": "existential_anxiety"}}]

  "My mother just died"
    → [{{"topic_id": "grief", "variant_id": "acute_grief"}}]

  "I still cry about my dad years later"
    → [{{"topic_id": "grief", "variant_id": "prolonged_grief"}}]

  "How can I believe without evidence?"
    → [{{"topic_id": "doubt", "variant_id": "intellectual_doubt"}}]

  "God feels completely silent and far away"
    → [{{"topic_id": "doubt", "variant_id": "existential_doubt"}}]

  "I feel anxious and God seems distant"
    → [{{"topic_id": "anxiety", "variant_id": null}}, {{"topic_id": "doubt", "variant_id": "existential_doubt"}}]

  "What's the weather today?"
    → []

Respond with ONLY the JSON array. No explanation, no markdown, no other text.\
"""
    return _system_prompt


def classify_intent(user_input: str) -> list[dict]:
    """Return a list of classification dicts matching the user input.

    Each dict has:
      - topic_id:  str  — a taxonomy topic ID
      - variant_id: str | None — a variant within that topic, or None if ambiguous

    Results are ordered by relevance, capped at 3. Fewer results indicate
    higher specificity. Returns an empty list on no match or any error.
    """
    try:
        response = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": _get_system_prompt(),
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

        out = []
        for item in result:
            if not isinstance(item, dict):
                continue
            topic_id = item.get("topic_id")
            if not isinstance(topic_id, str):
                continue
            variant_id = item.get("variant_id")
            if not isinstance(variant_id, (str, type(None))):
                variant_id = None
            out.append({"topic_id": topic_id, "variant_id": variant_id})

        return out[:3]

    except Exception:
        return []
