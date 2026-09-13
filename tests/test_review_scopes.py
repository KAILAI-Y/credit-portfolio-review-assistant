import math

import pandas as pd
import pytest

from core.review_scopes import (
    compare_scopes,
    incremental_metrics,
    scope_a_condition,
    scope_b_condition,
    scope_metrics,
)


def make_df(**overrides):
    base = {
        "ID": [1, 2, 3, 4, 5, 6],
        # PAY_0: -2 (A: no, B: no), 0 (no, no), 1 (no, yes -> increment),
        #        2 (yes, yes), 3 (yes, yes), -1 (no, no)
        "PAY_0": [-2, 0, 1, 2, 3, -1],
        "default.payment.next.month": [0, 1, 1, 1, 0, 0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# --- scope_metrics -----------------------------------------------------


def test_scope_a_metrics_match_manual_calculation():
    df = make_df()

    metrics = scope_metrics(df, scope_a_condition(df))

    # Scope A (PAY_0 >= 2): IDs 4, 5; positive labels: 1, 0
    assert metrics["clients"] == 2
    assert metrics["positive_labels"] == 1
    assert metrics["workload_share"] == pytest.approx(2 / 6)
    assert metrics["positive_label_coverage"] == pytest.approx(1 / 3)
    assert metrics["label_rate"] == pytest.approx(1 / 2)


def test_scope_b_metrics_match_manual_calculation():
    df = make_df()

    metrics = scope_metrics(df, scope_b_condition(df))

    # Scope B (PAY_0 > 0): IDs 3, 4, 5; positive labels: 1, 1, 0
    assert metrics["clients"] == 3
    assert metrics["positive_labels"] == 2
    assert metrics["workload_share"] == pytest.approx(3 / 6)
    assert metrics["positive_label_coverage"] == pytest.approx(2 / 3)
    assert metrics["label_rate"] == pytest.approx(2 / 3)


def test_scope_metrics_empty_selection_has_undefined_label_rate():
    df = make_df(PAY_0=[-2, -1, 0, -1, -2, 0])  # nobody meets scope A

    metrics = scope_metrics(df, scope_a_condition(df))

    assert metrics["clients"] == 0
    assert metrics["positive_labels"] == 0
    assert metrics["workload_share"] == 0.0
    assert metrics["positive_label_coverage"] == 0.0
    assert math.isnan(metrics["label_rate"])


def test_scope_metrics_zero_portfolio_positive_labels_has_undefined_coverage():
    df = make_df(**{"default.payment.next.month": [0, 0, 0, 0, 0, 0]})

    metrics = scope_metrics(df, scope_a_condition(df))

    assert metrics["clients"] == 2
    assert metrics["positive_labels"] == 0
    assert metrics["label_rate"] == 0.0
    assert math.isnan(metrics["positive_label_coverage"])


# --- incremental_metrics -----------------------------------------------------


def test_incremental_metrics_match_manual_calculation():
    df = make_df()
    condition_a = scope_a_condition(df)
    condition_b = scope_b_condition(df)

    increment = incremental_metrics(df, condition_a, condition_b)

    # B \ A: ID 3 only (PAY_0 == 1), positive label 1
    assert increment["clients"] == 1
    assert increment["positive_labels"] == 1
    assert increment["label_rate"] == pytest.approx(1.0)
    assert increment["coverage_gain"] == pytest.approx(1 / 3)


def test_incremental_metrics_empty_increment_is_undefined_rate():
    df = make_df(PAY_0=[-2, -1, 0, 2, 3, -1])  # nobody has PAY_0 == 1

    condition_a = scope_a_condition(df)
    condition_b = scope_b_condition(df)
    increment = incremental_metrics(df, condition_a, condition_b)

    assert increment["clients"] == 0
    assert increment["positive_labels"] == 0
    assert math.isnan(increment["label_rate"])
    assert increment["coverage_gain"] == 0.0


# --- compare_scopes ----------------------------------------------------------


def test_compare_scopes_scope_a_is_subset_of_scope_b():
    df = make_df()

    result = compare_scopes(df)

    assert result["scope_a_subset_of_scope_b"] is True
    assert result["scope_b"]["clients"] == result["scope_a"]["clients"] + result["increment"]["clients"]
    assert (
        result["scope_b"]["positive_labels"]
        == result["scope_a"]["positive_labels"] + result["increment"]["positive_labels"]
    )


def test_compare_scopes_empty_input():
    df = pd.DataFrame(columns=["ID", "PAY_0", "default.payment.next.month"])

    result = compare_scopes(df)

    assert result["scope_a"]["clients"] == 0
    assert result["scope_b"]["clients"] == 0
    assert result["scope_a_subset_of_scope_b"] is True
    assert math.isnan(result["scope_a"]["label_rate"])


# --- full dataset reconciliation ---------------------------------------------


def test_full_dataset_scope_comparison_matches_acceptance_criteria(full_dataset):
    result = compare_scopes(full_dataset)

    assert result["scope_a"]["clients"] == 3130
    assert result["scope_a"]["positive_labels"] == 2177

    assert result["scope_b"]["clients"] == 6818
    assert result["scope_b"]["positive_labels"] == 3429

    assert result["increment"]["clients"] == 3688
    assert result["increment"]["positive_labels"] == 1252

    assert result["scope_a_subset_of_scope_b"] is True


def test_full_dataset_scope_rates_are_unrounded_and_within_tolerance(full_dataset):
    result = compare_scopes(full_dataset)

    assert result["scope_a"]["label_rate"] == pytest.approx(2177 / 3130, abs=1e-9)
    assert result["scope_b"]["label_rate"] == pytest.approx(3429 / 6818, abs=1e-9)
    assert result["scope_a"]["positive_label_coverage"] == pytest.approx(2177 / 6636, abs=1e-9)
    assert result["scope_b"]["positive_label_coverage"] == pytest.approx(3429 / 6636, abs=1e-9)
