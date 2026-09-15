"""Offline tests for app/citation_validator.py.

No network or API call anywhere here - every check runs against a literal
draft string and a hand-built context dict.
"""

from __future__ import annotations

from app.citation_validator import (
    SUPPORTED_METADATA_SOURCE_IDS,
    allowed_source_ids,
    extract_citations,
    validate_citations,
)

SAMPLE_CONTEXT = {
    "dataset_context": {"population": "..."},
    "data_quality": {"warnings": []},
    "credit_limit_band_definitions": {"bands": []},
    "sections": [
        {"source_id": "portfolio_overview", "title": "...", "data": {}},
        {"source_id": "review_scope_comparison", "title": "...", "data": {}},
        {"source_id": "computed_facts", "title": "...", "data": {}},
    ],
    "limitations": ["..."],
}


# --- allowed_source_ids -------------------------------------------------------


def test_allowed_ids_include_section_ids_and_supported_metadata_keys():
    allowed = allowed_source_ids(SAMPLE_CONTEXT)

    assert "portfolio_overview" in allowed
    assert "review_scope_comparison" in allowed
    assert "computed_facts" in allowed
    assert SUPPORTED_METADATA_SOURCE_IDS <= allowed
    assert "dataset_context" in allowed
    assert "data_quality" in allowed
    assert "limitations" in allowed
    assert "credit_limit_band_definitions" in allowed


def test_allowed_ids_exclude_unrelated_metadata_keys():
    # metric_definitions is a real top-level context key but is not one of
    # the explicitly supported metadata sources - a citation to it should
    # still be rejected.
    allowed = allowed_source_ids(SAMPLE_CONTEXT)
    assert "metric_definitions" not in allowed


def test_allowed_ids_reflect_only_the_given_context_sections():
    small_context = {"sections": [{"source_id": "portfolio_overview", "data": {}}]}
    allowed = allowed_source_ids(small_context)
    assert "portfolio_overview" in allowed
    assert "review_scope_comparison" not in allowed


def test_supported_metadata_key_is_allowed_only_when_present_in_context():
    # "limitations" is a generally supported metadata source, but a context
    # that never supplied it must not let a draft cite it anyway.
    context_without_limitations = {
        "dataset_context": {"population": "..."},
        "sections": [{"source_id": "portfolio_overview", "data": {}}],
    }
    allowed = allowed_source_ids(context_without_limitations)
    assert "dataset_context" in allowed
    assert "limitations" not in allowed
    assert "data_quality" not in allowed
    assert "credit_limit_band_definitions" not in allowed


def test_all_four_metadata_keys_allowed_when_all_present():
    allowed = allowed_source_ids(SAMPLE_CONTEXT)
    assert SUPPORTED_METADATA_SOURCE_IDS <= allowed


# --- extract_citations: single and multiple, comma/semicolon, repeated prefix -


def test_extracts_a_single_citation():
    draft = "Total clients: 30,000 (source: portfolio_overview)."
    assert extract_citations(draft) == ["portfolio_overview"]


def test_extracts_multiple_citations_across_the_draft():
    draft = (
        "Clients: 30,000 (source: portfolio_overview). Rate: 22.12% "
        "(source: computed_facts)."
    )
    assert extract_citations(draft) == ["portfolio_overview", "computed_facts"]


def test_extracts_comma_separated_ids_within_one_citation_group():
    draft = "A trade-off (source: review_scope_comparison, computed_facts)."
    assert extract_citations(draft) == ["review_scope_comparison", "computed_facts"]


def test_extracts_semicolon_separated_ids_within_one_citation_group():
    draft = "A trade-off (source: review_scope_comparison; computed_facts)."
    assert extract_citations(draft) == ["review_scope_comparison", "computed_facts"]


def test_extracts_ids_with_a_repeated_source_prefix_on_later_items():
    draft = (
        "A trade-off (source: review_scope_comparison; source: computed_facts)."
    )
    assert extract_citations(draft) == ["review_scope_comparison", "computed_facts"]


def test_citation_matching_is_case_insensitive_on_the_source_label():
    draft = "Clients: 30,000 (Source: portfolio_overview)."
    assert extract_citations(draft) == ["portfolio_overview"]


def test_no_citation_present_extracts_nothing():
    assert extract_citations("No citations here at all.") == []


# --- validate_citations: valid cases ------------------------------------------


def test_single_valid_citation_passes():
    draft = "Clients: 30,000 (source: portfolio_overview)."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert result.is_valid
    assert result.issues == []
    assert result.unknown_ids == []


def test_multiple_valid_citations_across_the_draft_pass():
    draft = (
        "## Executive Summary\nClients: 30,000 (source: portfolio_overview). "
        "## Limitations\nScopes are exploratory (source: limitations)."
    )
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert result.is_valid


def test_multiple_ids_in_one_group_all_valid_passes():
    draft = "A trade-off (source: review_scope_comparison, computed_facts)."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert result.is_valid


# --- validate_citations: rejection cases --------------------------------------


def test_report_with_no_citations_is_rejected():
    result = validate_citations("A draft with no citations whatsoever.", SAMPLE_CONTEXT)
    assert not result.is_valid
    assert any("no citations" in issue.lower() for issue in result.issues)


def test_unknown_single_citation_is_rejected():
    draft = "Clients: 30,000 (source: nonexistent_section)."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.unknown_ids == ["nonexistent_section"]
    assert any("nonexistent_section" in issue for issue in result.issues)


def test_one_unknown_id_among_otherwise_valid_citations_fails_the_whole_draft():
    draft = (
        "Clients: 30,000 (source: portfolio_overview). "
        "Made up (source: not_a_real_id)."
    )
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.unknown_ids == ["not_a_real_id"]


def test_reviewscope_comparisons_parent_limitations_is_rejected():
    # A real ID ("review_scope_comparison") extended with trailing prose must
    # not be accepted via a substring/prefix match - only an exact match to
    # an allowed ID counts.
    draft = "A trade-off (source: review_scope_comparison's parent limitations)."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert "review_scope_comparison's parent limitations" in result.unknown_ids
    # And it must not be silently treated as either of the two real IDs it
    # was built from.
    assert "review_scope_comparison" not in result.unknown_ids


def test_partial_prefix_of_a_real_id_is_rejected_not_matched_loosely():
    draft = "Clients: 30,000 (source: portfolio)."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.unknown_ids == ["portfolio"]


def test_duplicate_unknown_ids_are_deduplicated_in_first_seen_order():
    draft = (
        "First (source: bad_id). Second (source: bad_id). "
        "Third (source: also_bad)."
    )
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.unknown_ids == ["bad_id", "also_bad"]


def test_cited_ids_preserve_order_and_duplicates_for_display():
    draft = "A (source: portfolio_overview). B (source: portfolio_overview)."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert result.cited_ids == ["portfolio_overview", "portfolio_overview"]


def test_citing_a_supported_metadata_key_absent_from_the_context_is_rejected():
    context_without_limitations = {
        "dataset_context": {"population": "..."},
        "sections": [{"source_id": "portfolio_overview", "data": {}}],
    }
    draft = "Scopes are exploratory (source: limitations)."
    result = validate_citations(draft, context_without_limitations)
    assert not result.is_valid
    assert result.unknown_ids == ["limitations"]


# --- validate_citations: empty / malformed citations --------------------------


def test_empty_citation_group_alone_is_rejected_as_malformed_not_as_uncited():
    draft = "Clients: 30,000 (source: )."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.malformed_count == 1
    assert any(
        "empty" in issue.lower() or "malformed" in issue.lower()
        for issue in result.issues
    )
    # Distinct from the "no citations found" case: a citation group was
    # present, just empty.
    assert not any("no citations" in issue.lower() for issue in result.issues)


def test_trailing_empty_item_in_a_multi_id_group_is_rejected():
    draft = "A trade-off (source: portfolio_overview, )."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.malformed_count == 1


def test_empty_citation_rejected_even_when_valid_citations_also_exist():
    draft = (
        "Clients: 30,000 (source: portfolio_overview). "
        "Something else (source: )."
    )
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.malformed_count == 1
    # The valid citation elsewhere in the draft does not mask the malformed one.
    assert "portfolio_overview" not in result.unknown_ids


def test_whitespace_only_citation_group_is_rejected():
    draft = "Clients: 30,000 (source:    )."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.malformed_count == 1


def test_multiple_malformed_citations_are_all_counted():
    draft = "A (source: ). B (source: , )."
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.malformed_count == 3


# --- validate_citations: unclosed citation groups -----------------------------


def test_unclosed_citation_group_after_a_valid_one_is_rejected():
    # Regression: a valid citation followed by an unclosed "(source: ..."
    # group used to pass validation, since the unclosed group simply never
    # matched the closed-group pattern and was silently ignored.
    draft = "Clients: 30,000 (source: portfolio_overview). Also (source: limitations"
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.unclosed_count == 1
    assert any("unclosed" in issue.lower() for issue in result.issues)
    # The valid citation earlier in the draft does not mask the unclosed one.
    assert "portfolio_overview" not in result.unknown_ids


def test_unclosed_citation_group_alone_is_rejected():
    draft = "Something (source: limitations"
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.unclosed_count == 1


def test_closed_multi_id_citation_groups_are_not_flagged_as_unclosed():
    # Supported multi-source syntax (comma, semicolon, repeated "source:"
    # prefix) must still pass cleanly - only a truly unclosed group fails.
    draft = (
        "A (source: portfolio_overview, computed_facts). "
        "B (source: review_scope_comparison; source: computed_facts)."
    )
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert result.is_valid
    assert result.unclosed_count == 0


def test_unclosed_group_count_reflects_number_of_unclosed_groups():
    draft = "First (source: limitations without a close. Second (source: also_open"
    result = validate_citations(draft, SAMPLE_CONTEXT)
    assert not result.is_valid
    assert result.unclosed_count == 2
