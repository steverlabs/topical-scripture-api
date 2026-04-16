# Topical Scripture API

A local prototype that accepts freeform pastoral questions, classifies them against a curated topic taxonomy, fetches relevant ESV passages, and returns Claude-generated pastoral framing specific to what the user wrote.

---

## Prerequisites

- Python 3.11+
- An [ESV API key](https://api.esv.org/) (free registration)
- An [Anthropic API key](https://console.anthropic.com/)

---

## Setup

```bash
cd scripture-api

# Create and activate virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Add your API keys to `.env`:

```
ESV_API_KEY=your_esv_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

`.env` is excluded from version control via `.gitignore`.

---

## Run the server

```bash
uvicorn main:app --reload
```

The server starts at `http://localhost:8000`. `--reload` restarts automatically when you edit source files.

---

## Endpoints

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### `POST /query`

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"input": "I cannot stop worrying about the future"}'
```

**Request body:**

| Field        | Type    | Required | Default | Description                        |
|--------------|---------|----------|---------|------------------------------------|
| `input`      | string  | yes      | —       | Freeform pastoral question or need |
| `max_topics` | integer | no       | 2       | Maximum number of topics to return |

**Response shape:**

```json
{
  "input": "original user text",
  "topics": [
    {
      "id": "anxiety",
      "name": "Anxiety",
      "passages": [
        {
          "reference": "Philippians 4:6–7",
          "text": "ESV passage text...",
          "weight": "primary",
          "rationale": "why the curator chose this passage",
          "context_note": "any hermeneutical caution",
          "framing": "Claude-generated pastoral framing specific to the user's input"
        }
      ],
      "caution_flags": [],
      "editorial_notes": ""
    }
  ],
  "message": null
}
```

If nothing matches: `{"input": "...", "topics": [], "message": "No matching topics found."}`

---

## Run the test script

With the server running in one terminal, open a second terminal and run:

```bash
python test_query.py
```

This sends 5 representative queries and prints the full JSON response for each.

---

## Project structure

```
scripture-api/
├── main.py          # FastAPI app — /health and /query endpoints
├── classifier.py    # Classifies user input into taxonomy topic IDs via Claude
├── esv.py           # Fetches passage text from the ESV API
├── taxonomy.py      # Loads data/taxonomy.json
├── data/
│   └── taxonomy.json    # Curated topic taxonomy with passages and metadata
├── test_query.py    # Integration test script
├── requirements.txt
└── .env             # API keys (not committed)
```

---

## How it works

1. **Classification** — `classify_intent()` sends the user input to Claude with the full topic list and intent examples. Claude returns a ranked JSON array of matching topic IDs (max 3).

2. **Passage retrieval** — For each matched topic, the primary-weighted passages are fetched from the ESV API in parallel.

3. **Pastoral framing** — Each passage is sent to Claude alongside the user's original input. Claude generates 2–3 sentences of framing that speaks to the user's specific situation rather than offering a generic gloss. These calls also run in parallel.

4. **Response assembly** — Topics, passages, curator rationale, caution flags, and framings are returned in a single structured response.

---

## Extending the taxonomy

Edit `data/taxonomy.json` to add topics or passages. Each topic follows this schema:

```json
{
  "id": "unique_string",
  "name": "Topic Name",
  "cluster": "Cluster Name",
  "description": "Pastoral description",
  "intent_examples": ["example phrase 1", "example phrase 2"],
  "passages": [
    {
      "reference": "Book Chapter:Verse",
      "weight": "primary|supporting|contextual",
      "rationale": "Why this passage fits",
      "context_note": "Any hermeneutical caution"
    }
  ],
  "caution_flags": [],
  "editorial_notes": ""
}
```

The classifier system prompt is rebuilt automatically the first time `classify_intent()` is called after the server starts, so no restart is required after editing the taxonomy — though a restart is the safest option if you rename or remove topic IDs.
