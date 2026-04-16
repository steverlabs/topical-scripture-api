import asyncio
import os
from typing import Optional

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from classifier import classify_intent
from esv import fetch_passage
from taxonomy import load_taxonomy

load_dotenv()

app = FastAPI()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    input: str
    max_topics: int = 2


class PassageOut(BaseModel):
    reference: str
    text: str
    weight: str
    rationale: str
    context_note: str
    framing: str


class TopicOut(BaseModel):
    id: str
    name: str
    variant_id: Optional[str] = None
    variant_label: Optional[str] = None
    passages: list[PassageOut]
    caution_flags: list[str]
    editorial_notes: str


class QueryResponse(BaseModel):
    input: str
    topics: list[TopicOut]
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Pastoral framing via Claude
# ---------------------------------------------------------------------------

_framing_client: anthropic.Anthropic | None = None

_FRAMING_SYSTEM = """\
You are a pastoral assistant helping people find relevant scripture for their struggles.

Given a user's situation and a scripture passage, write 2-3 sentences of pastoral framing that:
- Speaks directly to what the user wrote — use their specific language and situation
- Shows how this passage connects to their particular experience
- Is honest, warm, and grounded — not generic or formulaic
- Does not add unsolicited advice or spiritual pressure

Respond with only the framing text. No quotes, no headers, no preamble.\
"""


def _framing_client_instance() -> anthropic.Anthropic:
    global _framing_client
    if _framing_client is None:
        _framing_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _framing_client


def _generate_framing(user_input: str, reference: str, text: str, rationale: str) -> str:
    """Return a 2-3 sentence pastoral framing for one passage (blocking)."""
    try:
        response = _framing_client_instance().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": _FRAMING_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"User's situation: {user_input}\n\n"
                        f"Passage ({reference}):\n{text}\n\n"
                        f"Curator's note: {rationale}"
                    ),
                }
            ],
        )
        return next((b.text for b in response.content if b.type == "text"), "").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_variant(topic: dict, variant_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (variant_id, variant_label) for a topic, or (None, None) if not found."""
    if not variant_id:
        return None, None
    for v in topic.get("topic_variants", []):
        if v["id"] == variant_id:
            return v["id"], v["label"]
    return None, None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    # 1. Classify intent (blocking → thread)
    classifications: list[dict] = await asyncio.to_thread(classify_intent, req.input)

    if not classifications:
        return QueryResponse(
            input=req.input,
            topics=[],
            message="No matching topics found.",
        )

    # 2. Resolve topics from taxonomy
    taxonomy = load_taxonomy()
    topic_map = {t["id"]: t for t in taxonomy["topics"]}

    matched = []  # list of (topic_dict, variant_id)
    for cls in classifications[: req.max_topics]:
        topic = topic_map.get(cls["topic_id"])
        if topic:
            matched.append((topic, cls.get("variant_id")))

    if not matched:
        return QueryResponse(
            input=req.input,
            topics=[],
            message="No matching topics found.",
        )

    # 3. Collect primary passages across all matched topics, then fetch in parallel
    #    Each item: (matched_index, passage_dict)
    to_fetch = [
        (mi, p)
        for mi, (topic, _) in enumerate(matched)
        for p in topic["passages"]
        if p["weight"] == "primary"
    ]

    esv_results = await asyncio.gather(
        *[asyncio.to_thread(fetch_passage, p["reference"]) for _, p in to_fetch]
    )

    # 4. Generate framings for successfully fetched passages in parallel
    framing_tasks = []
    framing_meta = []
    for (mi, passage), esv in zip(to_fetch, esv_results):
        if esv["error"] is None:
            framing_tasks.append(
                asyncio.to_thread(
                    _generate_framing,
                    req.input,
                    esv["reference"],
                    esv["text"],
                    passage.get("rationale", ""),
                )
            )
            framing_meta.append((mi, passage, esv))

    framings = await asyncio.gather(*framing_tasks)

    # 5. Assemble per-topic passage lists
    topic_passages: list[list[PassageOut]] = [[] for _ in matched]
    for (mi, passage, esv), framing in zip(framing_meta, framings):
        topic_passages[mi].append(
            PassageOut(
                reference=esv["reference"],
                text=esv["text"],
                weight=passage.get("weight", "primary"),
                rationale=passage.get("rationale", ""),
                context_note=passage.get("context_note", ""),
                framing=framing,
            )
        )

    # 6. Build final response
    topics_out = []
    for mi, (topic, variant_id) in enumerate(matched):
        resolved_variant_id, variant_label = _resolve_variant(topic, variant_id)
        topics_out.append(
            TopicOut(
                id=topic["id"],
                name=topic["name"],
                variant_id=resolved_variant_id,
                variant_label=variant_label,
                passages=topic_passages[mi],
                caution_flags=topic.get("caution_flags", []),
                editorial_notes=topic.get("editorial_notes", ""),
            )
        )

    return QueryResponse(input=req.input, topics=topics_out)
