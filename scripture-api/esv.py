"""Fetches scripture passages from the ESV API."""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

_ESV_API_URL = "https://api.esv.org/v3/passage/text/"
_TIMEOUT = 10.0


def fetch_passage(reference: str) -> dict:
    """Fetch a passage from the ESV API.

    Returns a dict with:
      - reference: canonical reference string from the API
      - text:      passage text
      - error:     None on success, or an error message string
    """
    api_key = os.getenv("ESV_API_KEY", "")
    if not api_key:
        return {"reference": reference, "text": "", "error": "ESV_API_KEY not set"}

    params = {
        "q": reference,
        "include-headings": "false",
        "include-footnotes": "false",
        "include-verse-numbers": "true",
        "include-short-copyright": "true",
        "include-passage-references": "true",
    }

    try:
        resp = httpx.get(
            _ESV_API_URL,
            params=params,
            headers={"Authorization": f"Token {api_key}"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        passages = data.get("passages", [])
        if not passages:
            return {
                "reference": reference,
                "text": "",
                "error": f"No passage found for '{reference}'",
            }

        return {
            "reference": data.get("canonical", reference),
            "text": passages[0].strip(),
            "error": None,
        }

    except httpx.TimeoutException:
        return {"reference": reference, "text": "", "error": "ESV API request timed out"}
    except httpx.HTTPStatusError as e:
        return {
            "reference": reference,
            "text": "",
            "error": f"ESV API error {e.response.status_code}",
        }
    except Exception as e:
        return {"reference": reference, "text": "", "error": str(e)}
