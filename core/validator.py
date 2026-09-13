"""Data-quality validation for the credit portfolio dataset.

Mirrors the checks performed in the analysis notebook (Section 2.4-2.5):
required columns, client-ID integrity, numeric analysis fields, missing
values, and a binary outcome label. Repayment-status codes that are not
explained in the source description (for example ``PAY_0`` values of
``0`` or ``-2``) are reported as warnings, not treated as invalid data,
since no interpretation for them is documented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ID_COL = "ID"
LIMIT_COL = "LIMIT_BAL"
PAY0_COL = "PAY_0"
TARGET_COL = "default.payment.next.month"

REQUIRED_COLUMNS = (ID_COL, LIMIT_COL, PAY0_COL, TARGET_COL)
NUMERIC_COLUMNS = REQUIRED_COLUMNS
VALID_LABELS = {0, 1}

# Repayment-status codes explained in the source data dictionary:
# -1 = pay duly; 1-9 = payment delay of one to nine-or-more months.
# Codes outside this set (notably 0 and -2) are observed in the data
# but are not documented, and are flagged without an invented meaning.
DOCUMENTED_PAY_CODES = frozenset({-1, 1, 2, 3, 4, 5, 6, 7, 8, 9})


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    undocumented_pay0_codes: dict[float, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_portfolio(df: pd.DataFrame) -> ValidationResult:
    """Validate a portfolio DataFrame and return a ValidationResult.

    Does not mutate ``df``. Blocking issues are collected in ``errors``;
    informational issues (undocumented repayment codes) are collected in
    ``warnings`` and never used to invent a meaning for those codes.
    """
    result = ValidationResult()

    if df is None or df.empty:
        result.errors.append("Input dataset is empty.")
        return result

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        result.errors.append(
            "Missing required column(s): " + ", ".join(missing_columns)
        )
        # Further checks assume these columns exist.
        return result

    _check_id_column(df, result)
    _check_numeric_columns(df, result)
    _check_finite_numeric_values(df, result)
    _check_missing_values(df, result)
    _check_binary_labels(df, result)
    _check_pay0_integer_values(df, result)
    _check_undocumented_pay0_codes(df, result)

    return result


def _check_id_column(df: pd.DataFrame, result: ValidationResult) -> None:
    missing_ids = int(df[ID_COL].isnull().sum())
    if missing_ids:
        result.errors.append(
            f"Column '{ID_COL}' contains {missing_ids} missing value(s)."
        )

    duplicate_ids = int(df[ID_COL].duplicated().sum())
    if duplicate_ids:
        result.errors.append(
            f"Column '{ID_COL}' contains {duplicate_ids} duplicate value(s)."
        )


def _check_numeric_columns(df: pd.DataFrame, result: ValidationResult) -> None:
    for col in NUMERIC_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            result.errors.append(f"Column '{col}' must be numeric.")


def _check_finite_numeric_values(df: pd.DataFrame, result: ValidationResult) -> None:
    for col in NUMERIC_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue  # already reported by _check_numeric_columns

        values = df[col].dropna()
        non_finite = int((~np.isfinite(values)).sum())
        if non_finite:
            result.errors.append(
                f"Column '{col}' contains {non_finite} non-finite value(s) "
                "(inf or -inf)."
            )


def _check_missing_values(df: pd.DataFrame, result: ValidationResult) -> None:
    for col in REQUIRED_COLUMNS:
        if col == ID_COL:
            continue  # already reported by _check_id_column
        missing = int(df[col].isnull().sum())
        if missing:
            result.errors.append(
                f"Column '{col}' contains {missing} missing value(s)."
            )


def _check_binary_labels(df: pd.DataFrame, result: ValidationResult) -> None:
    if not pd.api.types.is_numeric_dtype(df[TARGET_COL]):
        return  # already reported as a non-numeric column error

    observed_labels = set(df[TARGET_COL].dropna().unique().tolist())
    invalid_labels = observed_labels - VALID_LABELS
    if invalid_labels:
        result.errors.append(
            f"Column '{TARGET_COL}' contains values other than 0/1: "
            + ", ".join(str(v) for v in sorted(invalid_labels))
        )


def _check_pay0_integer_values(df: pd.DataFrame, result: ValidationResult) -> None:
    if not pd.api.types.is_numeric_dtype(df[PAY0_COL]):
        return  # already reported as a non-numeric column error

    values = df[PAY0_COL].dropna()
    finite_values = values[np.isfinite(values)]  # non-finite already reported separately
    non_integer = finite_values[finite_values != finite_values.astype(int)]
    if len(non_integer):
        result.errors.append(
            f"Column '{PAY0_COL}' contains {len(non_integer)} non-integer "
            "value(s); repayment-status codes must be whole numbers."
        )


def _check_undocumented_pay0_codes(df: pd.DataFrame, result: ValidationResult) -> None:
    if not pd.api.types.is_numeric_dtype(df[PAY0_COL]):
        return  # already reported as a non-numeric column error

    # Only consider genuinely whole-number codes here: non-finite and
    # non-integer values are already reported as errors above, and must not
    # also be reported as merely "undocumented" codes.
    values = df[PAY0_COL].dropna()
    finite_values = values[np.isfinite(values)]
    integer_values = finite_values[finite_values == finite_values.astype(int)].astype(int)

    counts = integer_values.value_counts(dropna=True)
    undocumented = sorted(c for c in counts.index if c not in DOCUMENTED_PAY_CODES)
    if not undocumented:
        return

    result.undocumented_pay0_codes = {code: int(counts[code]) for code in undocumented}
    result.warnings.append(
        f"Column '{PAY0_COL}' contains code(s) not documented in the source "
        "description reviewed: "
        + ", ".join(str(c) for c in undocumented)
        + ". Retained without assigning an interpretation."
    )
