#!/usr/bin/env python3
"""Connectivity check for the Claude API configuration.

Loads credentials from `.env`, sends one short synthetic prompt with a
small output limit, and reports a short, generic success or failure
message. Never prints the API key, the model value, response text, or
raw exception details.

Usage (from the repository root, with the project's virtual environment
active):

    python scripts/check_claude_api.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]

CHECK_PROMPT = "Reply with only the single word: OK"
MAX_OUTPUT_TOKENS = 16
REQUEST_TIMEOUT_SECONDS = 30.0

# A model value that matches the API key, or is shaped like a secret key
# (e.g. an Anthropic or OpenAI-style API key prefix), indicates the two
# `.env` fields were mixed up rather than a real model ID.
SECRET_KEY_PREFIXES = ("sk-ant-", "sk-")


def _looks_like_secret(value: str) -> bool:
    return value.startswith(SECRET_KEY_PREFIXES)


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    model = os.environ.get("ANTHROPIC_MODEL")

    missing = [
        name
        for name, value in (
            ("ANTHROPIC_API_KEY", api_key),
            ("ANTHROPIC_MODEL", model),
        )
        if not value
    ]
    if missing:
        print(
            "Claude API check failed: missing required configuration. "
            "Copy .env.example to .env and fill in the values."
        )
        return 1

    if model == api_key or _looks_like_secret(model):
        print(
            "Claude API check failed: ANTHROPIC_MODEL looks like a secret "
            "key rather than a model ID. Check .env for a copy-paste mistake."
        )
        return 1

    import anthropic

    client = anthropic.Anthropic(
        api_key=api_key,
        max_retries=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    try:
        client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": CHECK_PROMPT}],
        )
    except anthropic.AuthenticationError:
        print("Claude API check failed: authentication error.")
        return 1
    except anthropic.NotFoundError:
        print("Claude API check failed: model or endpoint not found.")
        return 1
    except anthropic.RateLimitError:
        print("Claude API check failed: rate limited.")
        return 1
    except anthropic.APIConnectionError:
        print("Claude API check failed: connection error.")
        return 1
    except anthropic.APIStatusError:
        print("Claude API check failed: API error.")
        return 1

    print("Claude API check succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
