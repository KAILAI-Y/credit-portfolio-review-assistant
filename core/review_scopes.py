"""Review-scope comparisons and incremental metrics.

Reproduces the notebook's Section 5 candidate review scopes (Scope A:
``PAY_0 >= 2``; Scope B: ``PAY_0 > 0``) and Section 5.1's incremental
population (clients in Scope B but not in Scope A). These are
exploratory rules, not approved bank policies.
"""

from __future__ import annotations

import pandas as pd

from .metrics import PAY0_COL, TARGET_COL, safe_divide

SCOPE_A_LABEL = "Scope A: PAY_0 >= 2"
SCOPE_B_LABEL = "Scope B: PAY_0 > 0"


def scope_a_condition(df: pd.DataFrame, pay_col: str = PAY0_COL) -> pd.Series:
    return df[pay_col] >= 2


def scope_b_condition(df: pd.DataFrame, pay_col: str = PAY0_COL) -> pd.Series:
    return df[pay_col] > 0


def scope_metrics(
    df: pd.DataFrame,
    condition: pd.Series,
    target_col: str = TARGET_COL,
) -> dict:
    """Selected clients, workload share, coverage, and label rate for one scope."""
    total_clients = len(df)
    total_positives = int(df[target_col].sum()) if total_clients else 0

    selected_clients = int(condition.sum())
    selected_positives = (
        int(df.loc[condition, target_col].sum()) if selected_clients else 0
    )

    return {
        "clients": selected_clients,
        "positive_labels": selected_positives,
        "workload_share": safe_divide(selected_clients, total_clients),
        "positive_label_coverage": safe_divide(selected_positives, total_positives),
        "label_rate": safe_divide(selected_positives, selected_clients),
    }


def incremental_metrics(
    df: pd.DataFrame,
    condition_a: pd.Series,
    condition_b: pd.Series,
    target_col: str = TARGET_COL,
) -> dict:
    """Clients and positive labels added when expanding from scope A to scope B."""
    total_positives = int(df[target_col].sum()) if len(df) else 0

    additional_condition = condition_b & ~condition_a
    additional_clients = int(additional_condition.sum())
    additional_positives = (
        int(df.loc[additional_condition, target_col].sum())
        if additional_clients
        else 0
    )

    return {
        "clients": additional_clients,
        "positive_labels": additional_positives,
        "label_rate": safe_divide(additional_positives, additional_clients),
        "coverage_gain": safe_divide(additional_positives, total_positives),
    }


def compare_scopes(
    df: pd.DataFrame,
    target_col: str = TARGET_COL,
    pay_col: str = PAY0_COL,
) -> dict:
    """Scope A, Scope B, and incremental metrics, plus a subset-relationship check."""
    condition_a = scope_a_condition(df, pay_col)
    condition_b = scope_b_condition(df, pay_col)

    scope_a_is_subset_of_b = not (condition_a & ~condition_b).any()

    return {
        "scope_a": scope_metrics(df, condition_a, target_col),
        "scope_b": scope_metrics(df, condition_b, target_col),
        "increment": incremental_metrics(df, condition_a, condition_b, target_col),
        "scope_a_subset_of_scope_b": bool(scope_a_is_subset_of_b),
    }
