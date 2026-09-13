"""Shared portfolio metric calculations.

Reproduces the notebook's existing definitions (Sections 2.3, 3, and 4):
the overall portfolio baseline, the three-way repayment-status grouping,
the quartile-based credit-limit bands, and segment/stratified summaries.
Functions return numeric results and do not mutate their input
DataFrames; percentage formatting is left to the display layer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ID_COL = "ID"
LIMIT_COL = "LIMIT_BAL"
PAY0_COL = "PAY_0"
TARGET_COL = "default.payment.next.month"

# Quartile-based bands from the notebook's Section 4.2 (TWD 50,000 /
# 140,000 / 240,000 boundaries), right-inclusive.
LIMIT_BAND_BINS = [float("-inf"), 50000, 140000, 240000, float("inf")]
LIMIT_BAND_LABELS = [
    "<= 50,000",
    "50,000-140,000",
    "140,000-240,000",
    "> 240,000",
]


def safe_divide(numerator, denominator):
    """Return numerator / denominator, or NaN when the denominator is 0.

    An undefined rate (e.g. coverage with zero positive labels) must not
    silently become zero.
    """
    if denominator == 0:
        return float("nan")
    return numerator / denominator


def portfolio_overview(df: pd.DataFrame, target_col: str = TARGET_COL) -> dict:
    """Overall client count, positive-label count, and label rate."""
    total_clients = len(df)
    positive_labels = int(df[target_col].sum()) if total_clients else 0
    return {
        "total_clients": total_clients,
        "positive_labels": positive_labels,
        "label_rate": safe_divide(positive_labels, total_clients),
    }


def group_repayment_status(status) -> str:
    """Notebook Section 3's three-way repayment-status grouping.

    ``PAY_0 <= 0`` is a numeric grouping, not a confirmed "current" or
    "no-risk" category.
    """
    if status >= 2:
        return "PAY_0 >= 2"
    if status == 1:
        return "PAY_0 = 1"
    return "PAY_0 <= 0"


def repayment_status_groups(df: pd.DataFrame, pay_col: str = PAY0_COL) -> pd.Series:
    """Per-client repayment-status group, without modifying ``df``."""
    return df[pay_col].apply(group_repayment_status).rename("pay0_group")


def credit_limit_bands(df: pd.DataFrame, limit_col: str = LIMIT_COL) -> pd.Series:
    """Per-client credit-limit band, without modifying ``df``."""
    return pd.cut(
        df[limit_col],
        bins=LIMIT_BAND_BINS,
        labels=LIMIT_BAND_LABELS,
        right=True,
    ).rename("limit_band")


def segment_summary(
    df: pd.DataFrame,
    group: pd.Series,
    target_col: str = TARGET_COL,
) -> pd.DataFrame:
    """Client counts, positive labels, rate, and shares for one grouping.

    ``group`` must share ``df``'s index (e.g. the output of
    ``repayment_status_groups`` or ``credit_limit_bands``).
    """
    return stratified_summary(df, [group], target_col=target_col)


def stratified_summary(
    df: pd.DataFrame,
    groups: list[pd.Series],
    target_col: str = TARGET_COL,
) -> pd.DataFrame:
    """Client counts, positive labels, rate, and shares across one or more groupings.

    Segments with zero clients get a NaN label rate rather than zero,
    since the rate is undefined for an empty group.
    """
    total_clients = len(df)
    total_positives = int(df[target_col].sum()) if total_clients else 0

    working = df[[target_col]].copy()
    group_names = []
    for i, group in enumerate(groups):
        name = group.name or f"group_{i}"
        if not group.index.sort_values().equals(df.index.sort_values()):
            raise ValueError(
                f"Grouping '{name}' has an index that does not match the "
                "input DataFrame's index; cannot align group labels to rows."
            )
        # Assign by index (not position) so a reordered group Series still
        # lines up with the correct rows.
        working[name] = group
        group_names.append(name)

    is_categorical = all(
        isinstance(group.dtype, pd.CategoricalDtype) for group in groups
    )

    grouped = working.groupby(group_names, observed=not is_categorical)[target_col]
    summary = grouped.agg(total_clients="count", positive_labels="sum")
    summary["positive_labels"] = summary["positive_labels"].astype(int)

    summary["label_rate"] = [
        safe_divide(positives, clients)
        for positives, clients in zip(
            summary["positive_labels"], summary["total_clients"]
        )
    ]
    summary["portfolio_share"] = summary["total_clients"].apply(
        lambda clients: safe_divide(clients, total_clients)
    )
    summary["label_share"] = summary["positive_labels"].apply(
        lambda positives: safe_divide(positives, total_positives)
    )

    return summary
