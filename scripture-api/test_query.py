"""Manual integration test — sends 5 queries to the running server and prints results."""

import json
import sys

import httpx

BASE_URL = "http://localhost:8000"

QUERIES = [
    "I can't stop worrying about losing my job",
    "My mother passed away last month and I don't know how to cope",
    "I'm struggling to believe God is real",
    "I feel completely alone and like nobody cares",
    "Why would God let this happen to me",
]


def run():
    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=5)
        health.raise_for_status()
    except Exception as e:
        print(f"ERROR: server not reachable at {BASE_URL} — {e}")
        sys.exit(1)

    for i, text in enumerate(QUERIES, 1):
        print(f"\n{'='*70}")
        print(f"Query {i}: {text}")
        print("=" * 70)

        try:
            resp = httpx.post(
                f"{BASE_URL}/query",
                json={"input": text},
                timeout=60,
            )
            resp.raise_for_status()
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except httpx.TimeoutException:
            print("ERROR: request timed out")
        except httpx.HTTPStatusError as e:
            print(f"ERROR: HTTP {e.response.status_code} — {e.response.text}")
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    run()
