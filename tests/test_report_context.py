"""Tests for app/report_context.py.

Expected values for the small synthetic datasets are computed by hand in
each test's comments, independently of core/metrics.py and
core/review_scopes.py, so a bug shared between the calculation and the
test would not be masked.
"""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from app.report_context import (
    CREDIT_LIMIT_BAND_DEFINITIONS,
    SOURCE_ID_COMPUTED_FACTS,
    SOURCE_ID_CREDIT_LIMIT_SUMMARY,
    SOURCE_ID_PORTFOLIO_OVERVIEW,
    SOURCE_ID_REPAYMENT_STATUS_SUMMARY,
    SOURCE_ID_REVIEW_SCOPE_COMPARISON,
    SOURCE_ID_REVIEW_SCOPE_INCREMENT,
    SOURCE_ID_STRATIFIED_SUMMARY,
    build_report_context,
)

# Aggregate-only schemas: every record in these sections must contain
# exactly these keys - never an "ID" or any other individual-client field.
SEGMENT_RECORD_KEYS = {
    "total_clients",
    "positive_labels",
    "label_rate",
    "portfolio_share",
    "positive_label_coverage",
}
REPAYMENT_STATUS_RECORD_KEYS = SEGMENT_RECORD_KEYS | {"repayment_status_group"}
CREDIT_LIMIT_RECORD_KEYS = SEGMENT_RECORD_KEYS | {"credit_limit_band"}
STRATIFIED_RECORD_KEYS = SEGMENT_RECORD_KEYS | {
    "repayment_status_group",
    "credit_limit_band",
}


def _section(context: dict, source_id: str) -> dict:
    matches = [s for s in context["sections"] if s["source_id"] == source_id]
    assert len(matches) == 1, f"expected exactly one section with id {source_id!r}"
    return matches[0]


def _assert_strict_json_serializable(context: dict) -> None:
    serialized = json.dumps(context, allow_nan=False)
    # Round-trips back to an equal structure (sanity check, not just "didn't raise").
    assert json.loads(serialized) == context


# --- bundled dataset ---------------------------------------------------------


def test_bundled_dataset_matches_documented_acceptance_criteria(full_dataset):
    context = build_report_context(full_dataset)

    overview = _section(context, SOURCE_ID_PORTFOLIO_OVERVIEW)["data"]
    assert overview == {
        "total_clients": 30000,
        "positive_labels": 6636,
        "label_rate": pytest.approx(0.2212, abs=5e-5),
    }

    status_by_group = {
        row["repayment_status_group"]: row
        for row in _section(context, SOURCE_ID_REPAYMENT_STATUS_SUMMARY)["data"]
    }
    assert status_by_group["PAY_0 <= 0"]["total_clients"] == 23182
    assert status_by_group["PAY_0 <= 0"]["positive_labels"] == 3207
    assert status_by_group["PAY_0 = 1"]["total_clients"] == 3688
    assert status_by_group["PAY_0 = 1"]["positive_labels"] == 1252
    assert status_by_group["PAY_0 >= 2"]["total_clients"] == 3130
    assert status_by_group["PAY_0 >= 2"]["positive_labels"] == 2177

    limit_by_band = {
        row["credit_limit_band"]: row
        for row in _section(context, SOURCE_ID_CREDIT_LIMIT_SUMMARY)["data"]
    }
    assert limit_by_band["<= 50,000"]["total_clients"] == 7676
    assert limit_by_band["<= 50,000"]["positive_labels"] == 2440
    assert limit_by_band["50,000-140,000"]["total_clients"] == 7614
    assert limit_by_band["50,000-140,000"]["positive_labels"] == 1882
    assert limit_by_band["140,000-240,000"]["total_clients"] == 7643
    assert limit_by_band["140,000-240,000"]["positive_labels"] == 1326
    assert limit_by_band["> 240,000"]["total_clients"] == 7067
    assert limit_by_band["> 240,000"]["positive_labels"] == 988

    scope_data = _section(context, SOURCE_ID_REVIEW_SCOPE_COMPARISON)["data"]
    assert scope_data["scope_a"]["clients"] == 3130
    assert scope_data["scope_a"]["positive_labels"] == 2177
    assert scope_data["scope_b"]["clients"] == 6818
    assert scope_data["scope_b"]["positive_labels"] == 3429
    assert scope_data["scope_a_subset_of_scope_b"] is True

    increment_data = _section(context, SOURCE_ID_REVIEW_SCOPE_INCREMENT)["data"]
    assert increment_data["clients"] == 3688
    assert increment_data["positive_labels"] == 1252

    assert len(_section(context, SOURCE_ID_STRATIFIED_SUMMARY)["data"]) == 12

    _assert_strict_json_serializable(context)


def test_bundled_dataset_counts_preserved_as_integers(full_dataset):
    context = build_report_context(full_dataset)

    for source_id in (
        SOURCE_ID_REPAYMENT_STATUS_SUMMARY,
        SOURCE_ID_CREDIT_LIMIT_SUMMARY,
        SOURCE_ID_STRATIFIED_SUMMARY,
    ):
        for row in _section(context, source_id)["data"]:
            assert isinstance(row["total_clients"], int)
            assert isinstance(row["positive_labels"], int)
            # Rates are unrounded floats, not formatted strings.
            assert isinstance(row["label_rate"], float)

    overview = _section(context, SOURCE_ID_PORTFOLIO_OVERVIEW)["data"]
    assert isinstance(overview["total_clients"], int)
    assert isinstance(overview["positive_labels"], int)


# --- small synthetic dataset -------------------------------------------------


def _make_small_dataset(**overrides) -> pd.DataFrame:
    base = {
        "ID": [1, 2, 3, 4, 5, 6],
        "LIMIT_BAL": [20000, 60000, 150000, 250000, 50000, 140000],
        "PAY_0": [-2, 0, 1, 2, 3, -1],
        "default.payment.next.month": [0, 1, 1, 1, 0, 0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_small_synthetic_dataset_matches_hand_calculated_values():
    # Hand-worked expectations (not derived by calling core.metrics):
    #
    # Rows: ID / LIMIT_BAL / PAY_0 / label
    #  1 / 20000  / -2 / 0   -> PAY_0<=0, band "<= 50,000"
    #  2 / 60000  /  0 / 1   -> PAY_0<=0, band "50,000-140,000"
    #  3 / 150000 /  1 / 1   -> PAY_0=1,  band "140,000-240,000"
    #  4 / 250000 /  2 / 1   -> PAY_0>=2, band "> 240,000"
    #  5 / 50000  /  3 / 0   -> PAY_0>=2, band "<= 50,000" (right-inclusive)
    #  6 / 140000 / -1 / 0   -> PAY_0<=0, band "50,000-140,000" (right-inclusive)
    #
    # Portfolio: 6 clients, 3 positive labels -> rate 0.5.
    #
    # Repayment status:
    #   PAY_0<=0: rows 1,2,6 -> 3 clients, 1 positive (row2) -> rate 1/3
    #   PAY_0=1:  row 3      -> 1 client,  1 positive        -> rate 1.0
    #   PAY_0>=2: rows 4,5   -> 2 clients, 1 positive (row4) -> rate 0.5
    #
    # Credit-limit bands:
    #   <= 50,000:        rows 1,5 -> 2 clients, 0 positive -> rate 0.0
    #   50,000-140,000:   rows 2,6 -> 2 clients, 1 positive -> rate 0.5
    #   140,000-240,000:  row 3    -> 1 client,  1 positive -> rate 1.0
    #   > 240,000:        row 4    -> 1 client,  1 positive -> rate 1.0
    #
    # Review scopes:
    #   Scope A (PAY_0>=2): rows 4,5 -> 2 clients, 1 positive, workload 2/6,
    #                        coverage 1/3, rate 0.5
    #   Scope B (PAY_0>0):  rows 3,4,5 -> 3 clients, 2 positive, workload 3/6,
    #                        coverage 2/3, rate 2/3
    #   Increment (B \ A): row 3 only -> 1 client, 1 positive, rate 1.0,
    #                        coverage_gain 1/3

    df = _make_small_dataset()
    context = build_report_context(df)

    overview = _section(context, SOURCE_ID_PORTFOLIO_OVERVIEW)["data"]
    assert overview["total_clients"] == 6
    assert overview["positive_labels"] == 3
    assert overview["label_rate"] == pytest.approx(0.5)

    status_by_group = {
        row["repayment_status_group"]: row
        for row in _section(context, SOURCE_ID_REPAYMENT_STATUS_SUMMARY)["data"]
    }
    assert status_by_group["PAY_0 <= 0"]["total_clients"] == 3
    assert status_by_group["PAY_0 <= 0"]["positive_labels"] == 1
    assert status_by_group["PAY_0 <= 0"]["label_rate"] == pytest.approx(1 / 3)
    assert status_by_group["PAY_0 = 1"]["total_clients"] == 1
    assert status_by_group["PAY_0 = 1"]["positive_labels"] == 1
    assert status_by_group["PAY_0 = 1"]["label_rate"] == pytest.approx(1.0)
    assert status_by_group["PAY_0 >= 2"]["total_clients"] == 2
    assert status_by_group["PAY_0 >= 2"]["positive_labels"] == 1
    assert status_by_group["PAY_0 >= 2"]["label_rate"] == pytest.approx(0.5)

    limit_by_band = {
        row["credit_limit_band"]: row
        for row in _section(context, SOURCE_ID_CREDIT_LIMIT_SUMMARY)["data"]
    }
    assert limit_by_band["<= 50,000"]["total_clients"] == 2
    assert limit_by_band["<= 50,000"]["positive_labels"] == 0
    assert limit_by_band["<= 50,000"]["label_rate"] == pytest.approx(0.0)
    assert limit_by_band["50,000-140,000"]["total_clients"] == 2
    assert limit_by_band["50,000-140,000"]["positive_labels"] == 1
    assert limit_by_band["50,000-140,000"]["label_rate"] == pytest.approx(0.5)
    assert limit_by_band["140,000-240,000"]["total_clients"] == 1
    assert limit_by_band["140,000-240,000"]["positive_labels"] == 1
    assert limit_by_band["> 240,000"]["total_clients"] == 1
    assert limit_by_band["> 240,000"]["positive_labels"] == 1

    scope_data = _section(context, SOURCE_ID_REVIEW_SCOPE_COMPARISON)["data"]
    assert scope_data["scope_a"]["clients"] == 2
    assert scope_data["scope_a"]["positive_labels"] == 1
    assert scope_data["scope_a"]["workload_share"] == pytest.approx(2 / 6)
    assert scope_data["scope_a"]["positive_label_coverage"] == pytest.approx(1 / 3)
    assert scope_data["scope_a"]["label_rate"] == pytest.approx(0.5)
    assert scope_data["scope_b"]["clients"] == 3
    assert scope_data["scope_b"]["positive_labels"] == 2
    assert scope_data["scope_b"]["workload_share"] == pytest.approx(3 / 6)
    assert scope_data["scope_b"]["positive_label_coverage"] == pytest.approx(2 / 3)
    assert scope_data["scope_b"]["label_rate"] == pytest.approx(2 / 3)
    assert scope_data["scope_a_subset_of_scope_b"] is True

    increment_data = _section(context, SOURCE_ID_REVIEW_SCOPE_INCREMENT)["data"]
    assert increment_data["clients"] == 1
    assert increment_data["positive_labels"] == 1
    assert increment_data["label_rate"] == pytest.approx(1.0)
    assert increment_data["coverage_gain"] == pytest.approx(1 / 3)

    _assert_strict_json_serializable(context)


# --- undefined rates: zero portfolio-wide positive labels --------------------


def test_zero_positive_labels_makes_coverage_null_but_keeps_real_zero_rates():
    # All labels are 0: total_positives == 0 portfolio-wide.
    #  - label_rate/workload_share/portfolio_share stay real, defined zeros
    #    (their denominators - client counts - are still nonzero).
    #  - positive_label_coverage (and coverage_gain) become undefined (0/0)
    #    for every section, since the shared denominator (total positives)
    #    is 0. These must serialize as JSON null, never as 0.
    df = _make_small_dataset(**{"default.payment.next.month": [0, 0, 0, 0, 0, 0]})
    context = build_report_context(df)

    overview = _section(context, SOURCE_ID_PORTFOLIO_OVERVIEW)["data"]
    assert overview["positive_labels"] == 0
    assert overview["label_rate"] == 0.0  # real zero, not null

    for row in _section(context, SOURCE_ID_REPAYMENT_STATUS_SUMMARY)["data"]:
        assert row["positive_labels"] == 0
        assert row["label_rate"] == 0.0  # every group has >=1 client
        assert row["portfolio_share"] is not None
        assert row["positive_label_coverage"] is None  # 0 / 0 total positives

    for row in _section(context, SOURCE_ID_CREDIT_LIMIT_SUMMARY)["data"]:
        assert row["positive_labels"] == 0
        assert row["label_rate"] == 0.0
        assert row["positive_label_coverage"] is None

    scope_data = _section(context, SOURCE_ID_REVIEW_SCOPE_COMPARISON)["data"]
    assert scope_data["scope_a"]["clients"] == 2
    assert scope_data["scope_a"]["label_rate"] == 0.0  # 2 clients, 0 positives
    assert scope_data["scope_a"]["positive_label_coverage"] is None
    assert scope_data["scope_b"]["positive_label_coverage"] is None

    increment_data = _section(context, SOURCE_ID_REVIEW_SCOPE_INCREMENT)["data"]
    assert increment_data["label_rate"] == 0.0  # 1 client, 0 positives
    assert increment_data["coverage_gain"] is None

    _assert_strict_json_serializable(context)


# --- undefined rates: an empty review scope ----------------------------------


def test_empty_review_scope_makes_its_own_label_rate_null():
    # Nobody has PAY_0 >= 2, so Scope A selects 0 clients:
    #   workload_share = 0/4 = 0.0 (defined)
    #   positive_label_coverage = 0/2 = 0.0 (defined: 2 positives exist
    #     portfolio-wide, this scope just captured none of them)
    #   label_rate = 0/0 -> undefined -> null
    # Scope B (PAY_0 > 0) selects only ID 4 (PAY_0 == 1).
    # The "PAY_0 >= 2" repayment-status group has 0 clients and must be
    # omitted from the summary entirely, not fabricated with null/zero
    # values (segment_summary() only returns observed, non-categorical
    # groups).
    df = pd.DataFrame(
        {
            "ID": [1, 2, 3, 4],
            "LIMIT_BAL": [20000, 60000, 150000, 250000],
            "PAY_0": [-2, -1, 0, 1],
            "default.payment.next.month": [0, 1, 0, 1],
        }
    )
    context = build_report_context(df)

    status_groups = {
        row["repayment_status_group"]
        for row in _section(context, SOURCE_ID_REPAYMENT_STATUS_SUMMARY)["data"]
    }
    assert status_groups == {"PAY_0 <= 0", "PAY_0 = 1"}  # "PAY_0 >= 2" omitted

    scope_data = _section(context, SOURCE_ID_REVIEW_SCOPE_COMPARISON)["data"]
    assert scope_data["scope_a"]["clients"] == 0
    assert scope_data["scope_a"]["positive_labels"] == 0
    assert scope_data["scope_a"]["workload_share"] == 0.0
    assert scope_data["scope_a"]["positive_label_coverage"] == 0.0
    assert scope_data["scope_a"]["label_rate"] is None
    assert scope_data["scope_b"]["clients"] == 1
    assert scope_data["scope_b"]["positive_labels"] == 1
    assert scope_data["scope_b"]["label_rate"] == pytest.approx(1.0)
    assert scope_data["scope_a_subset_of_scope_b"] is True

    increment_data = _section(context, SOURCE_ID_REVIEW_SCOPE_INCREMENT)["data"]
    assert increment_data["clients"] == 1
    assert increment_data["positive_labels"] == 1
    assert increment_data["label_rate"] == pytest.approx(1.0)
    assert increment_data["coverage_gain"] == pytest.approx(0.5)

    _assert_strict_json_serializable(context)


# --- invalid input rejection --------------------------------------------------


def test_invalid_input_is_rejected():
    invalid_df = pd.DataFrame({"ID": [1, 2]})  # missing LIMIT_BAL, PAY_0, label

    with pytest.raises(ValueError):
        build_report_context(invalid_df)


def test_duplicate_ids_are_rejected():
    df = _make_small_dataset(ID=[1, 1, 3, 4, 5, 6])

    with pytest.raises(ValueError):
        build_report_context(df)


# --- stable, unique source IDs and aggregate-only output ---------------------


def test_source_ids_are_stable_and_unique():
    context = build_report_context(_make_small_dataset())

    source_ids = [section["source_id"] for section in context["sections"]]
    assert source_ids == [
        SOURCE_ID_PORTFOLIO_OVERVIEW,
        SOURCE_ID_REPAYMENT_STATUS_SUMMARY,
        SOURCE_ID_CREDIT_LIMIT_SUMMARY,
        SOURCE_ID_STRATIFIED_SUMMARY,
        SOURCE_ID_REVIEW_SCOPE_COMPARISON,
        SOURCE_ID_REVIEW_SCOPE_INCREMENT,
        SOURCE_ID_COMPUTED_FACTS,
    ]
    assert len(source_ids) == len(set(source_ids))  # no duplicates

    # The literal strings are the external contract for future report
    # citations - pin them down, not just the constant names.
    assert SOURCE_ID_PORTFOLIO_OVERVIEW == "portfolio_overview"
    assert SOURCE_ID_REPAYMENT_STATUS_SUMMARY == "repayment_status_summary"
    assert SOURCE_ID_CREDIT_LIMIT_SUMMARY == "credit_limit_summary"
    assert SOURCE_ID_STRATIFIED_SUMMARY == "stratified_summary"
    assert SOURCE_ID_REVIEW_SCOPE_COMPARISON == "review_scope_comparison"
    assert SOURCE_ID_REVIEW_SCOPE_INCREMENT == "review_scope_increment"
    assert SOURCE_ID_COMPUTED_FACTS == "computed_facts"

    # Calling again with different data must not change the ID set - IDs
    # identify the *kind* of summary, not a particular result.
    other_context = build_report_context(_make_small_dataset(ID=[10, 20, 30, 40, 50, 60]))
    other_ids = [section["source_id"] for section in other_context["sections"]]
    assert other_ids == source_ids


def test_output_is_aggregate_only():
    context = build_report_context(_make_small_dataset())

    # No client-identifying field anywhere in the per-record schemas.
    for row in _section(context, SOURCE_ID_REPAYMENT_STATUS_SUMMARY)["data"]:
        assert set(row.keys()) == REPAYMENT_STATUS_RECORD_KEYS
    for row in _section(context, SOURCE_ID_CREDIT_LIMIT_SUMMARY)["data"]:
        assert set(row.keys()) == CREDIT_LIMIT_RECORD_KEYS
    for row in _section(context, SOURCE_ID_STRATIFIED_SUMMARY)["data"]:
        assert set(row.keys()) == STRATIFIED_RECORD_KEYS

    forbidden_keys = {"id", "ID", "client_id", "customer_id"}

    def _walk(value):
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value.keys())
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(context)


# --- credit-limit band definitions -------------------------------------------


def test_credit_limit_band_definitions_are_documented():
    context = build_report_context(_make_small_dataset())

    definitions = context["credit_limit_band_definitions"]
    assert definitions == CREDIT_LIMIT_BAND_DEFINITIONS
    assert definitions["currency"] == "TWD"

    bands = definitions["bands"]
    assert [band["label"] for band in bands] == [
        "<= 50,000",
        "50,000-140,000",
        "140,000-240,000",
        "> 240,000",
    ]
    assert bands[0]["lower_bound_exclusive"] is None  # open-ended below
    assert bands[0]["upper_bound_inclusive"] == 50000
    assert bands[1]["lower_bound_exclusive"] == 50000
    assert bands[1]["upper_bound_inclusive"] == 140000
    assert bands[2]["lower_bound_exclusive"] == 140000
    assert bands[2]["upper_bound_inclusive"] == 240000
    assert bands[3]["lower_bound_exclusive"] == 240000
    assert bands[3]["upper_bound_inclusive"] is None  # open-ended above

    # These are fixed constants, not recomputed per input: identical
    # regardless of the data passed in.
    other_context = build_report_context(
        _make_small_dataset(LIMIT_BAL=[1, 2, 3, 4, 5, 6])
    )
    assert other_context["credit_limit_band_definitions"] == definitions

    # No stray non-finite float leaked through (would fail allow_nan=False).
    serialized = json.dumps(definitions, allow_nan=False)
    for band in json.loads(serialized)["bands"]:
        for bound in (band["lower_bound_exclusive"], band["upper_bound_inclusive"]):
            if bound is not None:
                assert math.isfinite(bound)


# --- strict JSON serialization -----------------------------------------------


def test_context_is_strictly_json_serializable_with_allow_nan_false(full_dataset):
    for df in (
        full_dataset,
        _make_small_dataset(),
        _make_small_dataset(**{"default.payment.next.month": [0, 0, 0, 0, 0, 0]}),
    ):
        context = build_report_context(df)
        # Must not raise - allow_nan=False rejects any raw NaN/Infinity that
        # slipped through _jsonify().
        serialized = json.dumps(context, allow_nan=False)
        assert isinstance(serialized, str)


# --- computed_facts: pre-derived, so the model cannot get them wrong --------
#
# Added after a live evaluation (Haiku 4.5, report-draft-v3) misreported the
# true highest stratified rate, reversed a code/count pairing, and omitted
# an incremental positive-label count. Expected values below are computed
# by hand, independently of core/metrics.py and core/review_scopes.py.


def test_stratified_extrema_finds_the_true_max_not_the_naive_lowest_band():
    # Hand-worked expectations:
    #   PAY_0>=2, <= 50,000:       2 clients, 1 positive -> rate 0.5
    #   PAY_0>=2, 50,000-140,000:  2 clients, 2 positive -> rate 1.0  (true max)
    #   PAY_0<=0, > 240,000:       3 clients, 0 positive -> rate 0.0 (true min)
    #   PAY_0=1,  140,000-240,000: 3 clients, 1 positive -> rate 1/3
    # The true max is NOT in the lowest credit-limit band, mirroring the
    # live-eval bug where a naive "lowest band = worst" assumption was wrong.
    df = pd.DataFrame(
        {
            "ID": range(1, 11),
            "LIMIT_BAL": [20000, 20000, 60000, 60000, 250000, 250000, 250000, 150000, 150000, 150000],
            "PAY_0": [2, 2, 2, 2, 0, 0, 0, 1, 1, 1],
            "default.payment.next.month": [0, 1, 1, 1, 0, 0, 0, 1, 0, 0],
        }
    )
    context = build_report_context(df)

    facts = _section(context, SOURCE_ID_COMPUTED_FACTS)["data"]
    extrema = facts["stratified_extrema"]

    assert extrema["max"]["repayment_status_group"] == "PAY_0 >= 2"
    assert extrema["max"]["credit_limit_band"] == "50,000-140,000"
    assert extrema["max"]["label_rate"] == pytest.approx(1.0)

    assert extrema["min"]["repayment_status_group"] == "PAY_0 <= 0"
    assert extrema["min"]["credit_limit_band"] == "> 240,000"
    assert extrema["min"]["label_rate"] == pytest.approx(0.0)

    _assert_strict_json_serializable(context)


def test_stratified_extrema_helper_returns_none_when_no_row_has_a_defined_rate():
    # build_report_context() always rejects an empty dataset before this
    # helper ever runs, so every real stratified row has at least one
    # client and thus a defined rate - this branch is otherwise
    # unreachable. Exercise the private helper directly with an
    # all-undefined input to confirm it still degrades safely.
    from app.report_context import _stratified_extrema

    all_undefined = pd.DataFrame(
        {"label_rate": [float("nan"), float("nan")]},
        index=pd.MultiIndex.from_tuples(
            [("PAY_0 <= 0", "<= 50,000"), ("PAY_0 = 1", "> 240,000")]
        ),
    )
    assert _stratified_extrema(all_undefined) == {"max": None, "min": None}


def test_undocumented_pay0_code_records_pair_each_code_with_its_own_count():
    # Hand-worked: code -2 appears on rows 1-2 (count 2); code 0 appears on
    # rows 3-7 (count 5); codes 1 and 2 are documented and must be excluded.
    # Distinct counts catch a reversed code/count pairing, which a live
    # evaluation previously produced.
    df = pd.DataFrame(
        {
            "ID": range(1, 10),
            "LIMIT_BAL": [100000] * 9,
            "PAY_0": [-2, -2, 0, 0, 0, 0, 0, 1, 2],
            "default.payment.next.month": [0, 1, 0, 1, 0, 1, 0, 0, 1],
        }
    )
    context = build_report_context(df)

    facts = _section(context, SOURCE_ID_COMPUTED_FACTS)["data"]
    assert facts["undocumented_pay0_codes"] == [
        {"pay0_code": -2, "client_count": 2},
        {"pay0_code": 0, "client_count": 5},
    ]

    _assert_strict_json_serializable(context)


def test_scope_increment_fact_matches_the_increment_section():
    # Reuses the hand-worked small dataset (see
    # test_small_synthetic_dataset_matches_hand_calculated_values): the
    # increment (Scope B \ Scope A) is row 3 only -> 1 client, 1 positive.
    context = build_report_context(_make_small_dataset())

    increment_data = _section(context, SOURCE_ID_REVIEW_SCOPE_INCREMENT)["data"]
    facts = _section(context, SOURCE_ID_COMPUTED_FACTS)["data"]

    assert facts["scope_increment"] == {
        "clients": increment_data["clients"],
        "positive_labels": increment_data["positive_labels"],
    }
    assert facts["scope_increment"] == {"clients": 1, "positive_labels": 1}


def test_computed_facts_match_bundled_dataset_documented_values(full_dataset):
    # Cross-check against the documented reference values for the bundled
    # dataset (test expectations, not values re-derived from the app).
    context = build_report_context(full_dataset)
    facts = _section(context, SOURCE_ID_COMPUTED_FACTS)["data"]

    extrema = facts["stratified_extrema"]
    assert extrema["max"]["repayment_status_group"] == "PAY_0 >= 2"
    assert extrema["max"]["credit_limit_band"] == "50,000-140,000"
    assert extrema["max"]["label_rate"] == pytest.approx(0.707436, abs=5e-6)

    assert facts["undocumented_pay0_codes"] == [
        {"pay0_code": -2, "client_count": 2759},
        {"pay0_code": 0, "client_count": 14737},
    ]

    assert facts["scope_increment"] == {"clients": 3688, "positive_labels": 1252}

    _assert_strict_json_serializable(context)
