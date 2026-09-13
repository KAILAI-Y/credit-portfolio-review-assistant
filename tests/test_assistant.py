"""Offline, mocked tests for app/assistant.py.

These tests never call the real Claude API - every ``client`` is a mock.
They verify request construction and this module's own response-handling
logic (success, empty response, truncation, refusal, API errors). They do
NOT and cannot validate the factual accuracy, quality, or grounding of any
real model output - that requires a live-model eval (SPECS.md Section 7:
"model-response checks"), which is out of scope here.
"""

from __future__ import annotations

import json
import traceback
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import pytest

from app.assistant import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_TIMEOUT_SECONDS,
    PROMPT_VERSION,
    REQUIRED_SECTIONS,
    ReportDraft,
    ReportGenerationError,
    generate_report_draft,
)

FAKE_MODEL = "claude-opus-5"

SAMPLE_CONTEXT = {
    "dataset_context": {"population": "Historical Taiwanese credit card clients."},
    "metric_definitions": {"label_rate": "Positive labels divided by clients."},
    "sections": [
        {
            "source_id": "portfolio_overview",
            "title": "Portfolio overview",
            "data": {"total_clients": 30000, "positive_labels": 6636, "label_rate": 0.2212},
        },
        {
            "source_id": "review_scope_increment",
            "title": "Incremental population: Scope A to Scope B",
            "data": {
                "clients": 3688,
                "positive_labels": 1252,
                "label_rate": 0.33947939262472887,
                "coverage_gain": 0.188667872212176,
            },
        },
    ],
    "limitations": ["Descriptive associations only, not causal effects."],
}


def _text_response(
    text: str = "## Executive Summary\n...",
    stop_reason: str = "end_turn",
    input_tokens: int = 500,
    output_tokens: int = 200,
    model: str = FAKE_MODEL,
):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        model=model,
    )


def _mock_client(response=None, side_effect=None):
    client = MagicMock()
    if side_effect is not None:
        client.messages.create.side_effect = side_effect
    else:
        client.messages.create.return_value = response or _text_response()
    return client


# --- request construction ----------------------------------------------------


def test_request_uses_the_given_model_and_bounded_max_tokens():
    client = _mock_client()

    generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)

    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == FAKE_MODEL
    assert kwargs["max_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS
    assert isinstance(kwargs["max_tokens"], int) and kwargs["max_tokens"] > 0


def test_system_prompt_requires_required_sections_and_source_citations():
    client = _mock_client()

    generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)

    _, kwargs = client.messages.create.call_args
    system_prompt = kwargs["system"]
    for heading in REQUIRED_SECTIONS:
        assert heading in system_prompt
    assert "source_id" in system_prompt
    assert "percentage point" in system_prompt.lower()
    assert "causal" in system_prompt.lower() or "causes" in system_prompt.lower()
    assert "null" in system_prompt.lower()
    # Display-only unit conversion (fraction -> % or pp, 2 decimal places) is
    # explicitly allowed, while deriving a new business metric stays banned -
    # these two rules must not contradict each other.
    assert "two decimal places" in system_prompt.lower()
    assert "new business metric" in system_prompt.lower()
    assert "display-only" in system_prompt.lower()
    # Concise word-count target, added after a live request hit the
    # output-token limit.
    assert "400-600 words" in system_prompt or "400-600" in system_prompt
    assert "words" in system_prompt.lower()


def test_system_prompt_guards_against_the_live_evaluation_findings():
    # Added after two live evals (Haiku 4.5, report-draft-v3) found: a false
    # "highest rate" claim, quartile language wrongly carried over from
    # credit-limit bands to repayment-status groups, an invented "current or
    # ahead" interpretation of an undocumented PAY_0 group, reversed
    # code/count pairing, "validated" used where the source only supports
    # "evaluated on the same sample", and an omitted incremental
    # positive-label count.
    client = _mock_client()

    generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)

    _, kwargs = client.messages.create.call_args
    system_prompt = kwargs["system"].lower()

    assert "quartile" in system_prompt
    assert "highest" in system_prompt and "lowest" in system_prompt
    assert "computed_facts" in system_prompt
    assert "stratified_extrema" in system_prompt
    assert "invent" in system_prompt and "interpretation" in system_prompt
    assert "same record" in system_prompt or "same count" in system_prompt
    assert "validated" in system_prompt
    assert "evaluated on the same historical sample" in system_prompt
    assert "additional" in system_prompt and "incremental" in system_prompt
    assert "never state one of these two counts without the other" in system_prompt


def test_user_message_embeds_the_supplied_context_verbatim():
    client = _mock_client()

    generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)

    _, kwargs = client.messages.create.call_args
    user_content = kwargs["messages"][0]["content"]
    assert kwargs["messages"][0]["role"] == "user"
    # The exact context (not a re-derived or summarized copy) is present.
    assert json.dumps(SAMPLE_CONTEXT) in user_content
    assert "portfolio_overview" in user_content
    assert "review_scope_increment" in user_content


def test_no_injected_client_constructs_one_with_no_retries_and_given_timeout(
    monkeypatch,
):
    import anthropic

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.messages.create.return_value = _text_response()
    monkeypatch.setattr(anthropic, "Anthropic", mock_client_cls)

    generate_report_draft(
        SAMPLE_CONTEXT, model=FAKE_MODEL, timeout=12.5
    )  # no `client=` kwarg

    _, kwargs = mock_client_cls.call_args
    assert kwargs["max_retries"] == 0
    assert kwargs["timeout"] == 12.5


# --- successful output --------------------------------------------------------


def test_successful_response_returns_draft_with_full_metadata():
    response = _text_response(
        text="## Executive Summary\nBody text (source: portfolio_overview).",
        stop_reason="end_turn",
        input_tokens=777,
        output_tokens=321,
    )
    client = _mock_client(response=response)

    result = generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)

    assert isinstance(result, ReportDraft)
    assert result.draft_markdown == (
        "## Executive Summary\nBody text (source: portfolio_overview)."
    )
    assert result.model == FAKE_MODEL
    assert result.requested_model == FAKE_MODEL
    assert result.prompt_version == PROMPT_VERSION
    assert result.input_tokens == 777
    assert result.output_tokens == 321
    assert result.stop_reason == "end_turn"


def test_response_model_is_recorded_separately_from_requested_model():
    # The API can serve a request under a different model than the alias
    # requested (e.g. routed to a pinned snapshot) - `model` must reflect
    # what actually served the response, not an echo of the request.
    response = _text_response(model="served-model-actual")
    client = _mock_client(response=response)

    result = generate_report_draft(
        SAMPLE_CONTEXT, model="requested-model-alias", client=client
    )

    assert result.requested_model == "requested-model-alias"
    assert result.model == "served-model-actual"


def test_multiple_text_blocks_are_concatenated():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="## Executive Summary\n"),
            SimpleNamespace(type="text", text="More text."),
        ],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=2),
        model=FAKE_MODEL,
    )
    client = _mock_client(response=response)

    result = generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)

    assert result.draft_markdown == "## Executive Summary\nMore text."


# --- failure handling: API errors --------------------------------------------

FAKE_SENSITIVE_DETAIL = "sk-ant-api03-should-never-appear-in-our-error-message"


def _api_status_error(anthropic_module, message: str, status_code: int):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status_code, request=request)
    return anthropic_module.APIStatusError(message, response=response, body=None)


@pytest.mark.parametrize(
    "make_error, expected_snippet",
    [
        (
            lambda a: a.AuthenticationError(
                f"key {FAKE_SENSITIVE_DETAIL}",
                response=httpx2.Response(
                    401, request=httpx2.Request("POST", "https://api.anthropic.com")
                ),
                body=None,
            ),
            "authentication",
        ),
        (
            lambda a: a.PermissionDeniedError(
                f"key {FAKE_SENSITIVE_DETAIL}",
                response=httpx2.Response(
                    403, request=httpx2.Request("POST", "https://api.anthropic.com")
                ),
                body=None,
            ),
            "permission",
        ),
        (
            lambda a: a.NotFoundError(
                f"model {FAKE_SENSITIVE_DETAIL} not found",
                response=httpx2.Response(
                    404, request=httpx2.Request("POST", "https://api.anthropic.com")
                ),
                body=None,
            ),
            "not found",
        ),
        (
            lambda a: a.RateLimitError(
                f"rate limited {FAKE_SENSITIVE_DETAIL}",
                response=httpx2.Response(
                    429, request=httpx2.Request("POST", "https://api.anthropic.com")
                ),
                body=None,
            ),
            "rate limited",
        ),
        (
            lambda a: a.APIConnectionError(
                message=f"connection failed {FAKE_SENSITIVE_DETAIL}",
                request=httpx2.Request("POST", "https://api.anthropic.com"),
            ),
            "connection",
        ),
        (
            lambda a: _api_status_error(a, f"server error {FAKE_SENSITIVE_DETAIL}", 500),
            "api error",
        ),
    ],
)
def test_api_errors_are_wrapped_without_exposing_raw_payloads(make_error, expected_snippet):
    import anthropic

    client = _mock_client(side_effect=make_error(anthropic))

    with pytest.raises(ReportGenerationError) as exc_info:
        generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)

    exc = exc_info.value
    message = str(exc)
    assert FAKE_SENSITIVE_DETAIL not in message
    assert expected_snippet in message.lower()

    # `str(exception)` alone can't catch a leak via exception chaining: a
    # standard formatted traceback also prints the __cause__ (and, unless
    # suppressed, the "direct cause" banner). Chaining must be suppressed
    # (`from None`) so the original SDK error never appears here either.
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    formatted = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    assert FAKE_SENSITIVE_DETAIL not in formatted


def test_client_initialization_failure_raises_sanitized_error(monkeypatch):
    import anthropic

    fake_init_error = ValueError(f"bad client config: {FAKE_SENSITIVE_DETAIL}")
    monkeypatch.setattr(
        anthropic, "Anthropic", MagicMock(side_effect=fake_init_error)
    )

    with pytest.raises(ReportGenerationError) as exc_info:
        generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL)  # no client= kwarg

    exc = exc_info.value
    assert "initializ" in str(exc).lower()
    assert FAKE_SENSITIVE_DETAIL not in str(exc)
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    formatted = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    assert FAKE_SENSITIVE_DETAIL not in formatted


# --- failure handling: empty / truncated / refused responses ----------------


def test_empty_response_raises_report_generation_error():
    response = _text_response(text="")
    client = _mock_client(response=response)

    with pytest.raises(ReportGenerationError, match="(?i)empty"):
        generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)


def test_whitespace_only_response_raises_report_generation_error():
    response = _text_response(text="   \n\t  ")
    client = _mock_client(response=response)

    with pytest.raises(ReportGenerationError, match="(?i)empty"):
        generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)


def test_no_text_blocks_raises_report_generation_error():
    response = SimpleNamespace(
        content=[],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=0),
    )
    client = _mock_client(response=response)

    with pytest.raises(ReportGenerationError, match="(?i)empty"):
        generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)


def test_truncated_response_raises_report_generation_error():
    response = _text_response(text="## Executive Summary\nCut off mid", stop_reason="max_tokens")
    client = _mock_client(response=response)

    with pytest.raises(ReportGenerationError, match="(?i)truncat"):
        generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)


def test_refusal_raises_report_generation_error():
    response = _text_response(text="", stop_reason="refusal")
    client = _mock_client(response=response)

    with pytest.raises(ReportGenerationError, match="(?i)declin"):
        generate_report_draft(SAMPLE_CONTEXT, model=FAKE_MODEL, client=client)


# --- module import must not touch credentials or the network ---------------


def test_default_timeout_and_max_tokens_are_finite_and_bounded():
    assert 0 < DEFAULT_MAX_OUTPUT_TOKENS <= 128_000
    assert 0 < DEFAULT_TIMEOUT_SECONDS < 600
