"""AI report-drafting backend (FR-04).

Turns the aggregate context built by ``app/report_context.py`` into a
management-report draft via the Claude API. This module never calculates a
portfolio metric itself - it only asks the model to explain numbers Python
has already computed (SPECS.md Reliability Requirements: "Python calculates
all portfolio metrics; the AI explains supplied results rather than
independently calculating core metrics").

Nothing at import time touches credentials or the network: constructing a
default client, and every API call, happens only inside
``generate_report_draft()``, and only when the caller does not inject its
own client. Tests always inject a mock client, so importing or testing this
module never reads `.env` or reaches the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import anthropic

# Bump whenever SYSTEM_PROMPT's instructions change in a way that could
# affect report content, so evaluation results stay attributable to a
# specific prompt (SPECS.md Section 7: "Record model identifier, evaluation
# date, and prompt version with AI evaluation results").
PROMPT_VERSION = "report-draft-v5"

DEFAULT_MAX_OUTPUT_TOKENS = 6144
DEFAULT_TIMEOUT_SECONDS = 60.0

REQUIRED_SECTIONS = (
    "## Executive Summary",
    "## Key Findings",
    "## Review-Scope Trade-offs",
    "## Limitations",
)

SYSTEM_PROMPT = f"""You are drafting one section of a management report for a \
historical credit-portfolio review. You will receive a JSON "context" \
object containing pre-calculated aggregate metrics, metric and \
credit-limit-band definitions, historical dataset context, and known \
limitations. Every number in it was already calculated in Python - you \
explain and organize these supplied results. Do not calculate, estimate, \
or infer any number that is not already present in the context.

Write a concise English Markdown draft of 400-600 words in total, with \
exactly these four sections, in this order, using these exact headings:
{REQUIRED_SECTIONS[0]}
{REQUIRED_SECTIONS[1]}
{REQUIRED_SECTIONS[2]}
{REQUIRED_SECTIONS[3]}

Rules:
- Every quantitative statement must be followed by a citation of the \
exact "source_id" of the context section it came from, in the form \
"(source: <source_id>)".
- Use only the metrics and values supplied in the context. Never invent, \
estimate, extrapolate, or derive a new business metric that is not \
already present in the context (for example, a ratio, difference, or \
trend between two supplied numbers), and never reference a client row \
or ID - the context contains aggregates only.
- Display-only unit conversion is allowed and expected, and is not a \
"new" metric: every supplied fraction is a plain proportion (e.g. \
0.2212). Convert each one for display by multiplying by 100 and rounding \
to exactly two decimal places. Write label_rate, portfolio_share, \
positive_label_coverage, and workload_share as percentages (e.g. \
"22.12%"). Write "coverage_gain" as percentage points instead (e.g. \
"18.87 percentage points" or "18.87 pp") - it is a *change* in coverage, \
not a coverage level, so it must never be labeled a plain percentage. Do \
not perform any other arithmetic on a supplied value.
- A metric value of null means that rate is undefined for that \
population (for example, zero clients or zero positive labels) - say it \
is undefined or not available. Never report a null value as zero, and \
never report a real, defined zero as unavailable.
- Do not state or imply that any factor causes a change in default risk, \
that reviewing clients or changing a credit limit prevents losses, or \
that a candidate review scope is approved bank policy. Describe every \
relationship as a historical, descriptive association only.
- Only describe a segmentation as derived from quartiles (or any other \
data-driven cutoff) if the context's own definitions say so. Never carry \
that description over to a different segmentation that the context \
defines as fixed categories instead.
- Never determine a "highest", "lowest", "most", or "least" claim yourself \
by comparing rows - the context's "computed_facts" section already gives \
the pre-verified extreme row(s) (for example, "stratified_extrema"). Use \
only that row's exact labels and value for such a claim, cited to \
"computed_facts", and do not make an equivalent claim about any other row.
- Always refer to a segment using its exact supplied label (for example, \
a repayment-status group's literal "PAY_0 ..." label, or a specific PAY_0 \
code). Never invent or substitute a plain-English interpretation of what a \
code or group means (e.g. "current", "ahead", "behind") - some codes are \
explicitly documented in the context as having no known interpretation.
- When citing a per-code count (for example, from "computed_facts"' \
undocumented-code records), state each code together only with the count \
from that same record. Never separate codes from their counts into two \
lists and recombine them from memory or in a different order.
- Never describe a review scope's real-world performance as "validated" \
or "confirmed". If the context states a scope was only assessed, tested, \
or evaluated on the same historical sample used for exploration, describe \
it exactly that way (e.g. "evaluated on the same historical sample") and \
say plainly that performance on new clients or later periods is unknown - \
never invert or soften a stated limitation.
- When describing a trade-off between two review scopes, state both the \
additional (incremental) number of clients and the additional number of \
positive labels involved in expanding from the narrower to the wider \
scope, whenever the context supplies them (for example, in \
"computed_facts"' scope_increment), in addition to any rates or shares. \
Never state one of these two counts without the other.
- If a business question is not answered by the supplied context, say \
plainly what information is missing rather than guessing or fabricating \
an answer."""


class ReportGenerationError(RuntimeError):
    """Raised when a report draft cannot be produced.

    The message is always a short, generic description - never the raw
    SDK exception payload, which could echo request contents or other
    sensitive details back to a log or UI.
    """


@dataclass(frozen=True)
class ReportDraft:
    """A generated report draft plus the metadata needed to evaluate it.

    ``model`` is the model that actually served the response
    (``response.model``), which can differ from ``requested_model`` (an
    alias, or a model the API routed to a fallback for).
    """

    draft_markdown: str
    model: str
    requested_model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    stop_reason: str


def _build_user_message(context: dict) -> str:
    # allow_nan=False: the context must already be JSON-clean (see
    # app/report_context.py); fail loudly here rather than silently send
    # a non-finite value to the model.
    context_json = json.dumps(context, allow_nan=False)
    return (
        "Draft the report section from this context object. Cite a "
        "source_id beside every quantitative statement.\n\n"
        f"```json\n{context_json}\n```"
    )


def generate_report_draft(
    context: dict,
    *,
    model: str,
    client: Any | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ReportDraft:
    """Generate a management-report draft grounded in ``context``.

    ``model`` must be explicitly supplied by the caller - this module has
    no hardcoded or environment-derived default. Pass ``client`` (e.g. a
    mock) for offline testing; when omitted, a real ``anthropic.Anthropic``
    client is constructed - with no automatic retries and the given
    timeout - only at call time, never at import time.

    Raises ``ReportGenerationError`` on any API failure, an empty
    response, or a response truncated by the output-token limit. Never
    returns a fabricated or partial draft in place of a real error.
    """
    if client is None:
        try:
            client = anthropic.Anthropic(max_retries=0, timeout=timeout)
        except Exception:
            # Suppress chaining (`from None`): a formatted traceback of the
            # raised error must never include the original exception's
            # message, which could contain SDK-internal configuration
            # details.
            raise ReportGenerationError(
                "Report generation failed: could not initialize the API client."
            ) from None

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(context)}],
        )
    except anthropic.AuthenticationError:
        raise ReportGenerationError(
            "Report generation failed: authentication error."
        ) from None
    except anthropic.PermissionDeniedError:
        raise ReportGenerationError(
            "Report generation failed: permission denied."
        ) from None
    except anthropic.NotFoundError:
        raise ReportGenerationError(
            "Report generation failed: model or endpoint not found."
        ) from None
    except anthropic.RateLimitError:
        raise ReportGenerationError("Report generation failed: rate limited.") from None
    except anthropic.APIConnectionError:
        raise ReportGenerationError(
            "Report generation failed: connection error."
        ) from None
    except anthropic.APIStatusError as e:
        raise ReportGenerationError(
            f"Report generation failed: API error (status {e.status_code})."
        ) from None
    except Exception:
        # Anything not modeled above (e.g. an SDK type this code doesn't
        # know about yet) - sanitize rather than let a raw payload surface.
        raise ReportGenerationError(
            "Report generation failed: unexpected error."
        ) from None

    if response.stop_reason == "refusal":
        raise ReportGenerationError(
            "Report generation failed: the model declined to respond."
        )
    if response.stop_reason == "max_tokens":
        raise ReportGenerationError(
            "Report generation failed: response was truncated at the "
            "output-token limit before completing."
        )

    draft_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    if not draft_text:
        raise ReportGenerationError("Report generation failed: empty response.")

    usage = response.usage
    return ReportDraft(
        draft_markdown=draft_text,
        model=response.model,
        requested_model=model,
        prompt_version=PROMPT_VERSION,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        stop_reason=response.stop_reason,
    )
