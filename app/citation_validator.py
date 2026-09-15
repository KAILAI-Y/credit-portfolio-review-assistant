"""Offline validation of a report draft's ``(source: <source_id>)`` citations.

Checks that every citation in a generated draft names a ``source_id`` the
draft could actually have been given - either a ``sections[*].source_id``
entry, or one of a small set of top-level metadata keys the system prompt
also permits citing (``dataset_context``, ``data_quality``, ``limitations``,
``credit_limit_band_definitions``). This is a purely offline, string-level
check: no network or API call is made here, and passing it does not mean a
citation is used correctly, only that the ID it names exists.

A passing result means every citation names a real ID and at least one
citation is present. It does NOT mean the draft is factually accurate, or
that any individual citation actually supports the claim it is attached to
- verifying that requires a human (or a live-model eval), not this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Top-level context keys - other than "sections" - that the system prompt
# (app/assistant.py's SYSTEM_PROMPT) allows a draft to cite, since they carry
# supporting facts a statement could legitimately be grounded in even though
# they are not part of the numbered "sections" list.
SUPPORTED_METADATA_SOURCE_IDS = frozenset(
    {
        "dataset_context",
        "data_quality",
        "limitations",
        "credit_limit_band_definitions",
    }
)

# Matches a whole "(source: ...)" citation group up to its closing
# parenthesis. Content inside is split further by _split_citation_group().
_CITATION_GROUP_RE = re.compile(r"\(\s*source\s*:\s*([^)]*)\)", re.IGNORECASE)

# Matches just the *opening* of a citation group, with no closing paren
# required - used to detect a "(source: ..." that never closes, which
# _CITATION_GROUP_RE would otherwise simply fail to match (and so ignore).
_CITATION_OPEN_RE = re.compile(r"\(\s*source\s*:", re.IGNORECASE)

# A "source:" prefix repeated on a later item within the same group, e.g.
# "(source: a; source: b)" rather than "(source: a; b)".
_REPEATED_PREFIX_RE = re.compile(r"^source\s*:\s*", re.IGNORECASE)


@dataclass(frozen=True)
class CitationValidationResult:
    """Result of validating a draft's citations against a context's IDs.

    ``is_valid`` is true only when at least one citation was found, none of
    them is empty or malformed, and every named citation is an ID in
    ``allowed_ids``. ``cited_ids`` preserves cited order and duplicates (for
    display), including any empty string from a malformed citation;
    ``unknown_ids`` is the subset of *non-empty* cited IDs not in
    ``allowed_ids``, deduplicated in first-seen order. ``malformed_count`` is
    the number of empty/malformed citations found (for example
    "(source: )" or a trailing empty item in "(source: a, )").
    ``unclosed_count`` is the number of "(source: ..." groups missing their
    closing ")" - these never reach ``cited_ids`` at all, since they cannot
    be parsed into an ID, so they are tracked and reported separately.
    """

    is_valid: bool
    allowed_ids: frozenset[str]
    cited_ids: list[str]
    unknown_ids: list[str]
    malformed_count: int = 0
    unclosed_count: int = 0
    issues: list[str] = field(default_factory=list)


def allowed_source_ids(context: dict) -> frozenset[str]:
    """The set of ``source_id`` values a draft grounded in ``context`` may cite.

    A metadata key (e.g. ``limitations``) is only allowed when it is
    actually present in ``context`` - a draft cannot legitimately cite a
    section the given context never supplied, even if that key is one of
    the generally supported metadata sources.
    """
    section_ids = {section["source_id"] for section in context.get("sections", [])}
    present_metadata_ids = {key for key in SUPPORTED_METADATA_SOURCE_IDS if key in context}
    return frozenset(section_ids | present_metadata_ids)


def _split_citation_group(group_text: str) -> list[str]:
    """Split one "(source: ...)" group's inner text into individual IDs.

    Handles comma- and semicolon-separated lists, and strips a repeated
    "source:" prefix from any item after the first (e.g. the second item in
    "source: a; source: b"). Returns candidate strings exactly as found,
    only whitespace-trimmed - never fuzzy-matched or truncated - so a
    citation naming extra trailing text (for example "review_scope_
    comparison's parent limitations") stays a single, distinct candidate
    that a later *exact* set-membership check will reject rather than
    silently accept because it starts with or contains a real ID.

    An item that is empty after stripping (for example a trailing comma in
    "(source: portfolio_overview, )", or "(source: )" alone) is kept as an
    empty string rather than dropped - a caller must treat it as a
    malformed citation, not as if it were simply never cited.
    """
    return [
        _REPEATED_PREFIX_RE.sub("", part.strip()).strip()
        for part in re.split(r"[,;]", group_text)
    ]


def extract_citations(draft_markdown: str) -> list[str]:
    """All cited IDs in ``draft_markdown``, in the order they appear."""
    cited: list[str] = []
    for match in _CITATION_GROUP_RE.finditer(draft_markdown):
        cited.extend(_split_citation_group(match.group(1)))
    return cited


def _unclosed_citation_snippets(draft_markdown: str, max_len: int = 40) -> list[str]:
    """Text starting at each "(source: ..." that never reaches a closing ")".

    Every closed citation group also starts with the same "(source:" opening,
    so any opening whose start position isn't among the closed matches' start
    positions is missing its closing paren - the rest of the draft (if any)
    never supplies one.
    """
    closed_starts = {match.start() for match in _CITATION_GROUP_RE.finditer(draft_markdown)}
    return [
        draft_markdown[match.start() : match.start() + max_len].strip()
        for match in _CITATION_OPEN_RE.finditer(draft_markdown)
        if match.start() not in closed_starts
    ]


def validate_citations(draft_markdown: str, context: dict) -> CitationValidationResult:
    """Validate every ``(source: ...)`` citation in ``draft_markdown``.

    Fails - with an explanatory issue - when no citation is present at all,
    when any citation is empty or malformed (for example "(source: )", or a
    blank item in a comma/semicolon-separated list), when a "(source: ..."
    group is missing its closing ")", or when any non-empty cited ID is not
    an exact match for one of ``context``'s allowed IDs (see
    ``allowed_source_ids``). An ID must match completely; a cited string
    that merely contains or starts with a real ID is treated as unknown,
    never accepted as a near-match. Any one of these failures fails the
    whole draft even when other, valid citations are also present.
    """
    allowed = allowed_source_ids(context)
    cited = extract_citations(draft_markdown)

    issues: list[str] = []
    if not cited:
        issues.append(
            "No citations found. Every quantitative statement must be "
            "followed by a \"(source: <source_id>)\" citation."
        )

    malformed_count = sum(1 for source_id in cited if not source_id)
    if malformed_count:
        issues.append(
            "Empty or malformed citation found (e.g. \"(source: )\" with "
            "no ID, or a blank item in a comma/semicolon-separated list)."
        )

    unclosed_snippets = _unclosed_citation_snippets(draft_markdown)
    for snippet in unclosed_snippets:
        issues.append(f'Unclosed citation group found: "{snippet}..." is missing its closing ")".')

    unknown_ids: list[str] = []
    for source_id in cited:
        if source_id and source_id not in allowed and source_id not in unknown_ids:
            unknown_ids.append(source_id)
    for source_id in unknown_ids:
        issues.append(f'Unknown citation source: "{source_id}".')

    return CitationValidationResult(
        is_valid=not issues,
        allowed_ids=allowed,
        cited_ids=cited,
        unknown_ids=unknown_ids,
        malformed_count=malformed_count,
        unclosed_count=len(unclosed_snippets),
        issues=issues,
    )
