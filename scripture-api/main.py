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
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    # 1. Classify intent (blocking → thread)
    topic_ids: list[str] = await asyncio.to_thread(classify_intent, req.input)

    if not topic_ids:
        return QueryResponse(
            input=req.input,
            topics=[],
            message="No matching topics found.",
        )

    # 2. Resolve topics from taxonomy
    taxonomy = load_taxonomy()
    topic_map = {t["id"]: t for t in taxonomy["topics"]}
    matched = [topic_map[tid] for tid in topic_ids[: req.max_topics] if tid in topic_map]

    # 3. Collect primary passages across all matched topics, then fetch in parallel
    #    Each item: (topic_index, passage_dict)
    to_fetch = [
        (ti, p)
        for ti, topic in enumerate(matched)
        for p in topic["passages"]
        if p["weight"] == "primary"
    ]

    esv_results = await asyncio.gather(
        *[asyncio.to_thread(fetch_passage, p["reference"]) for _, p in to_fetch]
    )

    # 4. Generate framings for successfully fetched passages in parallel
    framing_tasks = []
    framing_meta = []  # track which (topic_idx, passage_dict, esv) each task belongs to
    for (ti, passage), esv in zip(to_fetch, esv_results):
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
            framing_meta.append((ti, passage, esv))

    framings = await asyncio.gather(*framing_tasks)

    # 5. Assemble per-topic passage lists
    topic_passages: list[list[PassageOut]] = [[] for _ in matched]
    for (ti, passage, esv), framing in zip(framing_meta, framings):
        topic_passages[ti].append(
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
    topics_out = [
        TopicOut(
            id=topic["id"],
            name=topic["name"],
            passages=topic_passages[ti],
            caution_flags=topic.get("caution_flags", []),
            editorial_notes=topic.get("editorial_notes", ""),
        )
        for ti, topic in enumerate(matched)
    ]

    return QueryResponse(input=req.input, topics=topics_out)
