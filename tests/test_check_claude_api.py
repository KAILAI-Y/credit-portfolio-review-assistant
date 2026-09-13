"""Tests for scripts/check_claude_api.py.

All tests mock the Anthropic client and stub out `.env` loading, so no
real request is ever sent and the real `.env` file is never read.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import httpx2
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_claude_api.py"


def _load_module():
    """Load scripts/check_claude_api.py as an importable module.

    Loaded with a name other than ``"__main__"`` so the module's
    ``if __name__ == "__main__":`` guard never fires on import.
    """
    spec = importlib.util.spec_from_file_location("check_claude_api", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def check_module(monkeypatch):
    module = _load_module()
    # Never touch the real .env file; tests control the environment directly.
    monkeypatch.setattr(module, "load_dotenv", lambda path: None)
    return module


@pytest.fixture()
def mock_anthropic_client(monkeypatch):
    """Patch the real `anthropic.Anthropic` class and return the mock client instance."""
    import anthropic

    mock_client = MagicMock()
    mock_client_cls = MagicMock(return_value=mock_client)
    monkeypatch.setattr(anthropic, "Anthropic", mock_client_cls)
    return mock_client_cls, mock_client


def _make_api_status_error(anthropic_module, message: str, status_code: int = 400):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status_code, request=request)
    return anthropic_module.APIStatusError(message, response=response, body=None)


FAKE_API_KEY = "sk-ant-api03-not-a-real-key-0000000000000000000000"
FAKE_MODEL = "claude-opus-5"


# --- 1. Missing configuration sends no request ------------------------------


def test_missing_api_key_sends_no_request(check_module, mock_anthropic_client, monkeypatch, capsys):
    mock_client_cls, mock_client = mock_anthropic_client
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)

    exit_code = check_module.main()

    assert exit_code == 1
    mock_client_cls.assert_not_called()
    mock_client.messages.create.assert_not_called()
    captured = capsys.readouterr()
    assert "failed" in captured.out.lower()


def test_missing_model_sends_no_request(check_module, mock_anthropic_client, monkeypatch, capsys):
    mock_client_cls, mock_client = mock_anthropic_client
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    exit_code = check_module.main()

    assert exit_code == 1
    mock_client_cls.assert_not_called()
    mock_client.messages.create.assert_not_called()


def test_missing_configuration_message_is_generic(check_module, mock_anthropic_client, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    check_module.main()

    captured = capsys.readouterr()
    assert "ANTHROPIC_API_KEY" not in captured.out
    assert "ANTHROPIC_MODEL" not in captured.out


# --- 2. A fake key mistakenly used as the model sends no request and is not printed ---


def test_model_equal_to_api_key_is_rejected_without_request(
    check_module, mock_anthropic_client, monkeypatch, capsys
):
    mock_client_cls, mock_client = mock_anthropic_client
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_API_KEY)  # the mistake

    exit_code = check_module.main()

    assert exit_code == 1
    mock_client_cls.assert_not_called()
    mock_client.messages.create.assert_not_called()
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out


def test_model_shaped_like_a_secret_key_is_rejected_without_request(
    check_module, mock_anthropic_client, monkeypatch, capsys
):
    mock_client_cls, mock_client = mock_anthropic_client
    fake_model_secret = "sk-ant-api03-different-fake-value-1111111111"
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", fake_model_secret)

    exit_code = check_module.main()

    assert exit_code == 1
    mock_client_cls.assert_not_called()
    mock_client.messages.create.assert_not_called()
    captured = capsys.readouterr()
    assert fake_model_secret not in captured.out
    assert FAKE_API_KEY not in captured.out


# --- 3. API errors do not expose sensitive values ---------------------------


@pytest.mark.parametrize(
    "exception_factory",
    [
        lambda a, req: a.AuthenticationError(
            f"invalid key {FAKE_API_KEY}",
            response=httpx2.Response(401, request=req),
            body=None,
        ),
        lambda a, req: a.NotFoundError(
            f"model '{FAKE_API_KEY}' not found",
            response=httpx2.Response(404, request=req),
            body=None,
        ),
        lambda a, req: a.RateLimitError(
            f"rate limited for key {FAKE_API_KEY}",
            response=httpx2.Response(429, request=req),
            body=None,
        ),
        lambda a, req: a.APIConnectionError(
            message=f"connection failed for key {FAKE_API_KEY}", request=req
        ),
        lambda a, req: a.APIStatusError(
            f"server error, key={FAKE_API_KEY}",
            response=httpx2.Response(500, request=req),
            body=None,
        ),
    ],
)
def test_api_errors_do_not_expose_sensitive_values(
    check_module, mock_anthropic_client, monkeypatch, capsys, exception_factory
):
    import anthropic

    mock_client_cls, mock_client = mock_anthropic_client
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    mock_client.messages.create.side_effect = exception_factory(anthropic, request)

    exit_code = check_module.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert "failed" in captured.out.lower()
    # The client must still be constructed with no retries and a timeout.
    _, kwargs = mock_client_cls.call_args
    assert kwargs["max_retries"] == 0
    assert kwargs["timeout"] == check_module.REQUEST_TIMEOUT_SECONDS


# --- 4. A successful response produces a safe success message --------------


def test_successful_response_produces_a_safe_success_message(
    check_module, mock_anthropic_client, monkeypatch, capsys
):
    mock_client_cls, mock_client = mock_anthropic_client
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)
    mock_client.messages.create.return_value = MagicMock()

    exit_code = check_module.main()

    assert exit_code == 0
    mock_client.messages.create.assert_called_once()
    _, call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs["model"] == FAKE_MODEL
    assert call_kwargs["max_tokens"] == check_module.MAX_OUTPUT_TOKENS

    captured = capsys.readouterr()
    assert "succeeded" in captured.out.lower()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_MODEL not in captured.out
