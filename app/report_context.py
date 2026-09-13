"""Structured, JSON-serializable context for AI-assisted report generation.

Builds the aggregated data an AI report-drafting step (FR-04) would ground
its statements in. This module only assembles and JSON-sanitizes results
from the shared ``core`` calculation modules - it does not implement any
metric formula itself, and it does not call an AI model.

Every summary in the returned context carries a stable ``source_id`` so a
future report-generation prompt can cite exactly which calculation backs a
given statement (SPECS.md FR-04: "Reference the table or metric supporting
each quantitative finding"). Undefined rates (see
``core.metrics.safe_divide``) are converted to ``None`` rather than 0, and
all values are left unrounded; formatting is a presentation-layer concern
(see ``app/main.py``), not a concern of this module.

Only aggregate summaries are returned - never individual client rows or
IDs (SPECS.md Reliability Requirements: "Only necessary aggregate summaries
are sent to the model.").
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.metrics import (  # noqa: E402
    LIMIT_BAND_BINS,
    LIMIT_BAND_LABELS,
    credit_limit_bands,
    portfolio_overview,
    repayment_status_groups,
    segment_summary,
    stratified_summary,
)
from core.review_scopes import (  # noqa: E402
    SCOPE_A_LABEL,
    SCOPE_B_LABEL,
    compare_scopes,
)
from core.validator import ValidationResult, validate_portfolio  # noqa: E402

# Repayment-status display order (Section 3 of the notebook / core.metrics'
# group_repayment_status()). Not a calculation - core.metrics does not export
# an ordering constant for these three fixed category labels, unlike
# LIMIT_BAND_LABELS, so it is named here once for stable section ordering.
REPAYMENT_STATUS_GROUP_ORDER = ["PAY_0 <= 0", "PAY_0 = 1", "PAY_0 >= 2"]

SOURCE_ID_PORTFOLIO_OVERVIEW = "portfolio_overview"
SOURCE_ID_REPAYMENT_STATUS_SUMMARY = "repayment_status_summary"
SOURCE_ID_CREDIT_LIMIT_SUMMARY = "credit_limit_summary"
SOURCE_ID_STRATIFIED_SUMMARY = "stratified_summary"
SOURCE_ID_REVIEW_SCOPE_COMPARISON = "review_scope_comparison"
SOURCE_ID_REVIEW_SCOPE_INCREMENT = "review_scope_increment"
SOURCE_ID_COMPUTED_FACTS = "computed_facts"

DATASET_CONTEXT = {
    "population": "Historical Taiwanese credit card clients.",
    "period": (
        "April-September 2005 repayment history, with a next-month "
        "default-payment outcome label."
    ),
    "source": (
        "UCI Machine Learning Repository - Default of Credit Card Clients "
        "dataset (DOI 10.24432/C55S3H)."
    ),
    "caveat": (
        "Describes a 2005 historical sample; not an estimate of current "
        "credit risk."
    ),
}

METRIC_DEFINITIONS = {
    "label_rate": (
        "Positive labels divided by clients in the selected population "
        "or segment. Undefined (null) when the population has 0 clients."
    ),
    "portfolio_share": (
        "Selected clients divided by all clients in the portfolio."
    ),
    "positive_label_coverage": (
        "Selected positive labels divided by all positive labels in the "
        "portfolio. Undefined (null) when the portfolio has 0 positive "
        "labels."
    ),
    "workload_share": (
        "Selected clients, for a candidate review scope, divided by all "
        "clients."
    ),
    "coverage_gain": (
        "The additional positive-label coverage gained when expanding "
        "from Scope A to Scope B, as a fraction of all positive labels "
        "(multiply by 100 for percentage points)."
    ),
}

CREDIT_LIMIT_BAND_DEFINITIONS = {
    "currency": "TWD",
    "note": (
        "These are fixed exploratory bands derived from the original "
        "sample's credit-limit quartiles (TWD 50,000 / 140,000 / 240,000). "
        "They are constants reused as-is for every input dataset - never "
        "recalculated from the data passed in - and are not bank policy "
        "thresholds."
    ),
    "bands": [
        {
            "label": label,
            "lower_bound_exclusive": None if lower == float("-inf") else lower,
            "upper_bound_inclusive": None if upper == float("inf") else upper,
        }
        for label, lower, upper in zip(
            LIMIT_BAND_LABELS, LIMIT_BAND_BINS[:-1], LIMIT_BAND_BINS[1:]
        )
    ],
}

LIMITATIONS = [
    "Scope A (PAY_0 >= 2) and Scope B (PAY_0 > 0) are exploratory rules, "
    "not approved bank policies.",
    "Repayment-status codes 0 and -2 are not explained in the reviewed "
    "source description and are retained without an invented "
    "interpretation.",
    "Segment and review-scope comparisons describe statistical "
    "associations, not causal effects; they do not establish that "
    "changing a credit limit, or reviewing a client, changes default "
    "risk.",
    "Review scopes were assessed on the same historical sample used for "
    "exploration; their performance on new clients or later periods has "
    "not been validated.",
    "An undefined rate (for example, coverage with zero positive labels) "
    "is reported as null, never as zero.",
]


def _jsonify(value):
    """Recursively convert numpy/pandas scalars to native JSON-safe types.

    NaN (an undefined rate from ``safe_divide``) becomes ``None``. Does not
    round or otherwise alter numeric magnitude. Dict keys are coerced to
    ``str`` (for example ``undocumented_pay0_codes``' repayment-status
    codes) so the returned object is already JSON-shaped, rather than
    relying on ``json.dumps``'s own implicit int-key-to-string coercion.
    """
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return None if pd.isna(value) else value
    return value


def _stratified_extrema(stratified: pd.DataFrame) -> dict:
    """The stratified row(s) with the highest and lowest defined label_rate.

    Computed once in Python - rather than left for the model to compare
    across every stratified row itself - after a live evaluation found the
    model naming an incorrect row as the highest (SPECS.md Section 7: model
    quantitative claims must match calculation results). Rows with an
    undefined (null) label_rate - a zero-client credit-limit band - are
    excluded, matching how an undefined rate is never treated as a real
    zero elsewhere in this module. Returns ``None`` for both keys if no row
    has a defined rate.
    """
    defined_rates = stratified["label_rate"].dropna()
    if defined_rates.empty:
        return {"max": None, "min": None}

    def _row_fact(index) -> dict:
        status, band = index
        return {
            "repayment_status_group": status,
            "credit_limit_band": band,
            "label_rate": stratified.loc[index, "label_rate"],
        }

    return {
        "max": _row_fact(defined_rates.idxmax()),
        "min": _row_fact(defined_rates.idxmin()),
    }


def _ordered_subset(summary: pd.DataFrame, order: list) -> pd.DataFrame:
    """Reorder ``summary`` to match ``order``, dropping keys absent from it.

    Unlike ``.reindex(order)``, this never introduces an all-NaN row for a
    category with zero observed clients: ``segment_summary``/
    ``stratified_summary`` already include a real (non-fabricated) zero-count
    row for every categorical credit-limit band, and a genuinely absent,
    non-categorical repayment-status group is simply omitted rather than
    invented.
    """
    present = [key for key in order if key in summary.index]
    return summary.loc[present]


def build_report_context(df: pd.DataFrame) -> dict:
    """Build the JSON-serializable, aggregate-only context for FR-04.

    Validates ``df`` first (FR-01) and raises ``ValueError`` if it fails
    required checks, since a report must not be grounded in invalid data.
    Every numeric section is produced by the shared ``core`` calculation
    functions - no formula is reimplemented here.
    """
    validation_result: ValidationResult = validate_portfolio(df)
    if not validation_result.is_valid:
        raise ValueError(
            "Cannot build a report context from invalid data: "
            + " ".join(validation_result.errors)
        )

    overview = portfolio_overview(df)

    pay0_group = repayment_status_groups(df)
    status_summary = _ordered_subset(
        segment_summary(df, pay0_group), REPAYMENT_STATUS_GROUP_ORDER
    )
    # .itertuples(), not .iterrows(): a Series (one .iterrows() row) must have
    # a single dtype, so int columns would be silently upcast to float
    # alongside the rate columns. .itertuples() keeps each field's own dtype.
    repayment_status_records = [
        {
            "repayment_status_group": row.Index,
            "total_clients": int(row.total_clients),
            "positive_labels": int(row.positive_labels),
            "label_rate": row.label_rate,
            "portfolio_share": row.portfolio_share,
            "positive_label_coverage": row.label_share,
        }
        for row in status_summary.itertuples()
    ]

    limit_band = credit_limit_bands(df)
    limit_summary = _ordered_subset(
        segment_summary(df, limit_band), LIMIT_BAND_LABELS
    )
    credit_limit_records = [
        {
            "credit_limit_band": row.Index,
            "total_clients": int(row.total_clients),
            "positive_labels": int(row.positive_labels),
            "label_rate": row.label_rate,
            "portfolio_share": row.portfolio_share,
            "positive_label_coverage": row.label_share,
        }
        for row in limit_summary.itertuples()
    ]

    stratified_order = [
        (status, band)
        for status in REPAYMENT_STATUS_GROUP_ORDER
        for band in LIMIT_BAND_LABELS
    ]
    stratified = _ordered_subset(
        stratified_summary(df, [pay0_group, limit_band]), stratified_order
    )
    stratified_records = [
        {
            "repayment_status_group": row.Index[0],
            "credit_limit_band": row.Index[1],
            "total_clients": int(row.total_clients),
            "positive_labels": int(row.positive_labels),
            "label_rate": row.label_rate,
            "portfolio_share": row.portfolio_share,
            "positive_label_coverage": row.label_share,
        }
        for row in stratified.itertuples()
    ]

    scope_comparison = compare_scopes(df)

    computed_facts = {
        "stratified_extrema": _stratified_extrema(stratified),
        # Explicit (code, count) records - not a bare mapping - so the
        # model cannot transpose a code with another code's count (SPECS.md
        # Section 7: a live evaluation found exactly this reversal).
        "undocumented_pay0_codes": [
            {"pay0_code": code, "client_count": count}
            for code, count in sorted(validation_result.undocumented_pay0_codes.items())
        ],
        "scope_increment": {
            "clients": scope_comparison["increment"]["clients"],
            "positive_labels": scope_comparison["increment"]["positive_labels"],
        },
    }

    context = {
        "dataset_context": DATASET_CONTEXT,
        "metric_definitions": METRIC_DEFINITIONS,
        "credit_limit_band_definitions": CREDIT_LIMIT_BAND_DEFINITIONS,
        "data_quality": {
            "warnings": validation_result.warnings,
            "undocumented_pay0_codes": validation_result.undocumented_pay0_codes,
        },
        "sections": [
            {
                "source_id": SOURCE_ID_PORTFOLIO_OVERVIEW,
                "title": "Portfolio overview",
                "data": overview,
            },
            {
                "source_id": SOURCE_ID_REPAYMENT_STATUS_SUMMARY,
                "title": "Repayment-status summary",
                "data": repayment_status_records,
            },
            {
                "source_id": SOURCE_ID_CREDIT_LIMIT_SUMMARY,
                "title": "Credit-limit summary",
                "data": credit_limit_records,
            },
            {
                "source_id": SOURCE_ID_STRATIFIED_SUMMARY,
                "title": (
                    "Stratified summary (repayment status x credit-limit band)"
                ),
                "data": stratified_records,
            },
            {
                "source_id": SOURCE_ID_REVIEW_SCOPE_COMPARISON,
                "title": "Review-scope comparison",
                "data": {
                    "scope_a": {"label": SCOPE_A_LABEL, **scope_comparison["scope_a"]},
                    "scope_b": {"label": SCOPE_B_LABEL, **scope_comparison["scope_b"]},
                    "scope_a_subset_of_scope_b": scope_comparison[
                        "scope_a_subset_of_scope_b"
                    ],
                },
            },
            {
                "source_id": SOURCE_ID_REVIEW_SCOPE_INCREMENT,
                "title": "Incremental population: Scope A to Scope B",
                "data": scope_comparison["increment"],
            },
            {
                "source_id": SOURCE_ID_COMPUTED_FACTS,
                "title": "Computed report facts (pre-derived; do not recompute)",
                "data": computed_facts,
            },
        ],
        "limitations": LIMITATIONS,
    }

    return _jsonify(context)
