import math

import pandas as pd
import pytest

from core.metrics import (
    credit_limit_bands,
    group_repayment_status,
    portfolio_overview,
    repayment_status_groups,
    segment_summary,
    stratified_summary,
)


def make_df(**overrides):
    base = {
        "ID": [1, 2, 3, 4, 5, 6],
        "LIMIT_BAL": [20000, 60000, 150000, 250000, 50000, 140000],
        "PAY_0": [-2, 0, 1, 2, 3, -1],
        "default.payment.next.month": [0, 1, 1, 1, 0, 0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# --- portfolio_overview ---------------------------------------------------


def test_portfolio_overview_counts_and_rate():
    overview = portfolio_overview(make_df())

    assert overview["total_clients"] == 6
    assert overview["positive_labels"] == 3
    assert overview["label_rate"] == pytest.approx(3 / 6)


def test_portfolio_overview_empty_input_rate_is_undefined():
    df = pd.DataFrame(columns=["ID", "LIMIT_BAL", "PAY_0", "default.payment.next.month"])

    overview = portfolio_overview(df)

    assert overview["total_clients"] == 0
    assert overview["positive_labels"] == 0
    assert math.isnan(overview["label_rate"])


def test_portfolio_overview_zero_positive_labels_is_a_real_zero_rate():
    df = make_df(**{"default.payment.next.month": [0, 0, 0, 0, 0, 0]})

    overview = portfolio_overview(df)

    assert overview["positive_labels"] == 0
    assert overview["label_rate"] == 0.0
    assert not math.isnan(overview["label_rate"])


# --- group_repayment_status ------------------------------------------------


@pytest.mark.parametrize(
    "status,expected",
    [
        (-2, "PAY_0 <= 0"),
        (-1, "PAY_0 <= 0"),
        (0, "PAY_0 <= 0"),
        (1, "PAY_0 = 1"),
        (2, "PAY_0 >= 2"),
        (8, "PAY_0 >= 2"),
    ],
)
def test_group_repayment_status_boundaries(status, expected):
    assert group_repayment_status(status) == expected


def test_repayment_status_groups_does_not_mutate_input():
    df = make_df()
    original_columns = list(df.columns)

    repayment_status_groups(df)

    assert list(df.columns) == original_columns


# --- credit_limit_bands -----------------------------------------------------


@pytest.mark.parametrize(
    "limit,expected_band",
    [
        (50000, "<= 50,000"),
        (50001, "50,000-140,000"),
        (140000, "50,000-140,000"),
        (140001, "140,000-240,000"),
        (240000, "140,000-240,000"),
        (240001, "> 240,000"),
    ],
)
def test_credit_limit_band_boundaries(limit, expected_band):
    df = pd.DataFrame({"LIMIT_BAL": [limit]})

    band = credit_limit_bands(df)

    assert str(band.iloc[0]) == expected_band


def test_credit_limit_bands_does_not_mutate_input():
    df = make_df()
    original_columns = list(df.columns)

    credit_limit_bands(df)

    assert list(df.columns) == original_columns


# --- segment_summary ---------------------------------------------------


def test_segment_summary_matches_manual_calculation():
    df = make_df()
    group = repayment_status_groups(df)

    summary = segment_summary(df, group)

    row = summary.loc["PAY_0 <= 0"]
    # PAY_0 in {-2, 0, -1} -> IDs 1, 2, 6; labels 0, 1, 0
    assert row["total_clients"] == 3
    assert row["positive_labels"] == 1
    assert row["label_rate"] == pytest.approx(1 / 3)
    assert row["portfolio_share"] == pytest.approx(3 / 6)
    assert row["label_share"] == pytest.approx(1 / 3)


def test_segment_summary_reconciles_with_portfolio():
    df = make_df()
    group = repayment_status_groups(df)

    summary = segment_summary(df, group)
    overview = portfolio_overview(df)

    assert summary["total_clients"].sum() == overview["total_clients"]
    assert summary["positive_labels"].sum() == overview["positive_labels"]


def test_segment_summary_zero_positive_labels_in_dataset_gives_undefined_share():
    df = make_df(**{"default.payment.next.month": [0, 0, 0, 0, 0, 0]})
    group = repayment_status_groups(df)

    summary = segment_summary(df, group)

    assert (summary["positive_labels"] == 0).all()
    assert summary["label_share"].isna().all()
    # A group's own label_rate is still a defined zero (it has clients).
    assert (summary["label_rate"] == 0.0).all()


def test_credit_limit_band_summary_includes_empty_bands_with_undefined_rate():
    # No client falls in the "> 240,000" band.
    df = make_df(LIMIT_BAL=[10000, 20000, 30000, 40000, 45000, 49000])
    band = credit_limit_bands(df)

    summary = segment_summary(df, band)

    empty_band = summary.loc["> 240,000"]
    assert empty_band["total_clients"] == 0
    assert math.isnan(empty_band["label_rate"])


# --- stratified_summary -----------------------------------------------------


def test_stratified_summary_reconciles_with_portfolio():
    df = make_df()
    pay_group = repayment_status_groups(df)
    limit_band = credit_limit_bands(df)

    summary = stratified_summary(df, [pay_group, limit_band])
    overview = portfolio_overview(df)

    assert summary["total_clients"].sum() == overview["total_clients"]
    assert summary["positive_labels"].sum() == overview["positive_labels"]


def test_segment_summary_realigns_a_reordered_group_by_index():
    df = make_df()
    group = repayment_status_groups(df)
    reordered_group = group.iloc[::-1]  # same labels, reversed row order

    summary = segment_summary(df, group)
    summary_from_reordered = segment_summary(df, reordered_group)

    pd.testing.assert_frame_equal(summary, summary_from_reordered)


def test_stratified_summary_realigns_a_reordered_group_by_index():
    df = make_df()
    pay_group = repayment_status_groups(df)
    limit_band = credit_limit_bands(df)

    summary = stratified_summary(df, [pay_group, limit_band])
    summary_from_reordered = stratified_summary(
        df, [pay_group.iloc[::-1], limit_band.iloc[::-1]]
    )

    pd.testing.assert_frame_equal(summary, summary_from_reordered)


def test_stratified_summary_rejects_a_group_with_a_mismatched_index():
    df = make_df()
    group = repayment_status_groups(df)
    mismatched_group = group.copy()
    mismatched_group.index = mismatched_group.index + 100  # no overlap with df.index

    with pytest.raises(ValueError, match="pay0_group"):
        stratified_summary(df, [mismatched_group])


# --- full dataset reconciliation -------------------------------------------


def test_full_dataset_portfolio_overview(full_dataset):
    overview = portfolio_overview(full_dataset)

    assert overview["total_clients"] == 30000
    assert overview["positive_labels"] == 6636
    assert overview["label_rate"] == pytest.approx(0.2212, abs=5e-5)


def test_full_dataset_repayment_status_segments_reconcile(full_dataset):
    group = repayment_status_groups(full_dataset)
    summary = segment_summary(full_dataset, group)

    assert summary["total_clients"].sum() == 30000
    assert summary["positive_labels"].sum() == 6636

    over_two = summary.loc["PAY_0 >= 2"]
    assert over_two["total_clients"] == 3130
    assert over_two["positive_labels"] == 2177


def test_full_dataset_credit_limit_segments_reconcile(full_dataset):
    band = credit_limit_bands(full_dataset)
    summary = segment_summary(full_dataset, band)

    assert summary["total_clients"].sum() == 30000
    assert summary["positive_labels"].sum() == 6636


def test_full_dataset_stratified_segments_reconcile(full_dataset):
    pay_group = repayment_status_groups(full_dataset)
    limit_band = credit_limit_bands(full_dataset)
    summary = stratified_summary(full_dataset, [pay_group, limit_band])

    assert summary["total_clients"].sum() == 30000
    assert summary["positive_labels"].sum() == 6636
