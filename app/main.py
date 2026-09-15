"""Credit Portfolio Review Assistant - Streamlit page.

Loads the bundled historical dataset, runs the shared data-quality
validator (FR-01), and displays the overall portfolio baseline (FR-02).
Reuses core/validator.py and core/metrics.py rather than recalculating
anything locally.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import dotenv
import matplotlib

matplotlib.use("Agg")  # non-interactive backend, required for reliable rendering on macOS
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.assistant import ReportGenerationError, generate_report_draft  # noqa: E402
from app.citation_validator import validate_citations  # noqa: E402
from app.report_context import build_report_context  # noqa: E402
from core.metrics import (  # noqa: E402
    LIMIT_BAND_LABELS,
    credit_limit_bands,
    portfolio_overview,
    repayment_status_groups,
    segment_summary,
    stratified_summary,
)
from core.review_scopes import SCOPE_A_LABEL, SCOPE_B_LABEL, compare_scopes  # noqa: E402
from core.validator import validate_portfolio  # noqa: E402

DATA_PATH = REPO_ROOT / "data" / "UCI_Credit_Card.csv"

REPAYMENT_STATUS_GROUP_ORDER = ["PAY_0 <= 0", "PAY_0 = 1", "PAY_0 >= 2"]

# Same palette as the notebook's Section 3 chart (analysis/notebooks/
# credit-card-portfolio-risk-review.ipynb).
REPAYMENT_STATUS_GROUP_COLORS = ["#A8BAC8", "#6497B1", "#087E83"]
BASELINE_COLOR = "#B95237"


def _format_rate(value: float) -> str:
    """Format a 0-1 rate as a percentage, or "N/A" when it is undefined."""
    return "N/A" if pd.isna(value) else f"{value:.2%}"


def _format_percentage_points(value: float) -> str:
    """Format a 0-1 value as percentage points (e.g. "18.87 pp"), or "N/A"."""
    return "N/A" if pd.isna(value) else f"{value * 100:.2f} pp"


# st.table renders string values as Markdown, where a leading ">" is
# interpreted as a blockquote. This only renames the label for display;
# the underlying category, credit_limit_bands(), and LIMIT_BAND_LABELS
# are unchanged.
CREDIT_LIMIT_BAND_DISPLAY_LABELS = {"> 240,000": "Above 240,000"}


def _display_band_label(label: str) -> str:
    return CREDIT_LIMIT_BAND_DISPLAY_LABELS.get(label, label)


st.set_page_config(page_title="Credit Portfolio Review Assistant")

st.title("Credit Portfolio Review Assistant")
st.caption(
    "Historical sample: Taiwanese credit card clients, April-September 2005, "
    "with a next-month default-payment outcome label. Not current portfolio risk."
)

df = pd.read_csv(DATA_PATH)

validation_result = validate_portfolio(df)

for warning in validation_result.warnings:
    st.warning(warning)

if not validation_result.is_valid:
    st.error("Data validation failed. Analysis is blocked until these issues are resolved:")
    for error in validation_result.errors:
        st.error(error)
    st.stop()

overview = portfolio_overview(df)

col1, col2, col3 = st.columns(3)
col1.metric("Total clients", f"{overview['total_clients']:,}")
col2.metric("Positive-label count", f"{overview['positive_labels']:,}")
col3.metric("Observed default-label rate", f"{overview['label_rate']:.2%}")

st.subheader("Repayment-status summary")

pay0_group = repayment_status_groups(df)
status_summary = segment_summary(df, pay0_group).reindex(REPAYMENT_STATUS_GROUP_ORDER)

status_display = pd.DataFrame(
    {
        "Total clients": status_summary["total_clients"].map("{:,}".format),
        "Positive-label count": status_summary["positive_labels"].map("{:,}".format),
        "Observed default-label rate": status_summary["label_rate"].map(_format_rate),
        "Portfolio share": status_summary["portfolio_share"].map(_format_rate),
        "Positive-label coverage": status_summary["label_share"].map(_format_rate),
    },
    index=status_summary.index,
)
status_display.index.name = "Repayment status"

st.table(status_display)
st.caption(
    "A group's default-label rate is the share of its own clients with a "
    "positive label; positive-label coverage is that group's share of all "
    "positive labels across the whole portfolio."
)

st.subheader("Repayment-status default-label rate chart")

rates_pct = status_summary["label_rate"] * 100
baseline_pct = overview["label_rate"] * 100

fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(
    REPAYMENT_STATUS_GROUP_ORDER,
    rates_pct,
    color=REPAYMENT_STATUS_GROUP_COLORS,
)

ax.axhline(
    baseline_pct,
    color=BASELINE_COLOR,
    linestyle="--",
    label=f"Overall sample: {baseline_pct:.2f}%",
)

for bar, rate, clients in zip(bars, rates_pct, status_summary["total_clients"]):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 2,
        f"{rate:.2f}%\nn = {clients:,}",
        ha="center",
        fontsize=10,
    )

ax.set_title("Next-month default-label rate by repayment-status group")
ax.set_xlabel("Repayment-status group")
ax.set_ylabel("Default-label rate")
ax.set_ylim(0, 100)
ax.yaxis.set_major_formatter(mticker.PercentFormatter())
ax.legend()

st.pyplot(fig)
plt.close(fig)

st.subheader("Credit-limit summary")

limit_band = credit_limit_bands(df)
limit_summary = segment_summary(df, limit_band).reindex(LIMIT_BAND_LABELS)

limit_display = pd.DataFrame(
    {
        "Total clients": limit_summary["total_clients"].map("{:,}".format),
        "Positive-label count": limit_summary["positive_labels"].map("{:,}".format),
        "Observed default-label rate": limit_summary["label_rate"].map(_format_rate),
        "Portfolio share": limit_summary["portfolio_share"].map(_format_rate),
        "Positive-label coverage": limit_summary["label_share"].map(_format_rate),
    },
    index=limit_summary.index,
)
# Rename the index after construction: passing a relabeled index directly
# to the constructor would realign each (still originally-indexed) column
# Series against it, turning the renamed row into all-NaN.
limit_display.index = limit_display.index.map(_display_band_label)
limit_display.index.name = "Credit-limit band"

st.table(limit_display)
st.caption(
    "Credit limits are in TWD (New Taiwan dollars). Bands use the original "
    "sample's quartile boundaries and are exploratory groupings, not bank "
    "policy thresholds."
)

st.subheader("Stratified summary")

STRATIFIED_ORDER = [
    (status, band)
    for status in REPAYMENT_STATUS_GROUP_ORDER
    for band in LIMIT_BAND_LABELS
]

stratified = stratified_summary(df, [pay0_group, limit_band]).reindex(STRATIFIED_ORDER)
stratified_flat = stratified.reset_index()

stratified_display = pd.DataFrame(
    {
        "Repayment-status group": stratified_flat["pay0_group"],
        "Credit-limit band": stratified_flat["limit_band"].map(_display_band_label),
        "Total clients": stratified_flat["total_clients"].map("{:,}".format),
        "Positive-label count": stratified_flat["positive_labels"].map("{:,}".format),
        "Observed default-label rate": stratified_flat["label_rate"].map(_format_rate),
    }
)

st.table(stratified_display)
st.caption(
    "Compare credit-limit bands within the same repayment-status group. "
    "These are descriptive associations, not causal effects."
)

st.subheader("Review-scope comparison")

scope_comparison = compare_scopes(df)
scope_rows = {
    SCOPE_A_LABEL: scope_comparison["scope_a"],
    SCOPE_B_LABEL: scope_comparison["scope_b"],
}
scope_summary = pd.DataFrame.from_dict(scope_rows, orient="index")

scope_display = pd.DataFrame(
    {
        "Clients selected": scope_summary["clients"].map("{:,}".format),
        "Workload share": scope_summary["workload_share"].map(_format_rate),
        "Positive-label count": scope_summary["positive_labels"].map("{:,}".format),
        "Positive-label coverage": scope_summary["positive_label_coverage"].map(_format_rate),
        "Observed default-label rate": scope_summary["label_rate"].map(_format_rate),
    },
    index=scope_summary.index,
)
scope_display.index.name = "Review scope"

st.table(scope_display)
st.caption(
    "These are candidate review scopes evaluated against historical "
    "outcomes, not evidence that reviewing clients prevents defaults."
)

st.subheader("Incremental population: Scope A to Scope B")

increment = scope_comparison["increment"]

# horizontal=True wraps onto new lines in a narrow panel, unlike a fixed
# st.columns() row.
with st.container(horizontal=True):
    st.metric("Additional clients to review", f"{increment['clients']:,}")
    st.metric("Additional positive labels", f"{increment['positive_labels']:,}")
    st.metric(
        "Observed label rate among additional clients",
        _format_rate(increment["label_rate"]),
    )
    st.metric(
        "Positive-label coverage gain",
        _format_percentage_points(increment["coverage_gain"]),
    )

st.caption(
    "The additional population consists of clients selected by Scope B "
    "but not Scope A."
)

st.subheader("AI report draft")
st.caption(
    "Drafts a management-report section from the aggregate metrics above, "
    "using the Claude API. This is a draft for human review, not a final "
    "report - verify every statement before use."
)

# override=False: an already-set environment variable (e.g. exported by the
# shell, or by whatever process launched Streamlit) always wins over the
# repository .env file.
dotenv.load_dotenv(REPO_ROOT / ".env", override=False)

REPORT_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
REPORT_MODEL = os.environ.get("ANTHROPIC_MODEL")

if "report_draft" not in st.session_state:
    st.session_state.report_draft = None
if "citation_validation" not in st.session_state:
    st.session_state.citation_validation = None

if not REPORT_API_KEY or not REPORT_MODEL:
    st.info(
        "AI report drafting is not configured. Set ANTHROPIC_API_KEY and "
        "ANTHROPIC_MODEL (see .env.example) to enable this feature."
    )
else:
    generate_clicked = st.button("Generate report draft")
    just_generated = False

    if generate_clicked:
        with st.spinner("Generating report draft..."):
            try:
                report_context = build_report_context(df)
                new_draft = generate_report_draft(report_context, model=REPORT_MODEL)
            except ReportGenerationError as e:
                st.error(str(e))
            else:
                st.session_state.report_draft = new_draft
                # Validated once, offline, against the same context the draft
                # was grounded in - never re-sent to the API on failure; a
                # failed check is surfaced for human review, not auto-retried.
                st.session_state.citation_validation = validate_citations(
                    new_draft.draft_markdown, report_context
                )
                just_generated = True

    draft = st.session_state.report_draft
    validation = st.session_state.citation_validation
    if draft is not None and validation is None:
        # A draft with no stored validation (e.g. session state from before
        # offline citation validation existed) is validated now, offline,
        # against the current data - never by regenerating the draft or
        # calling the API again.
        validation = validate_citations(draft.draft_markdown, build_report_context(df))
        st.session_state.citation_validation = validation

    if draft is not None:
        if just_generated:
            st.success("Report draft generated.")
        st.caption(
            f"**Draft - requires review.** Model: `{draft.model}` | "
            f"Prompt version: `{draft.prompt_version}`"
        )

        draft_col, validation_col = st.columns([3, 1])
        with draft_col:
            st.markdown(draft.draft_markdown)
        with validation_col:
            st.subheader("Citation check")
            if validation.is_valid:
                # st.info, not st.success: this banner isn't tied to a fresh
                # generation event, so it must not be confused with (or
                # accidentally counted alongside) the one-time "Report draft
                # generated." success message above.
                st.info("All citations reference a known source ID.")
            else:
                st.error("Citation validation failed.")
                for issue in validation.issues:
                    st.warning(issue)
            st.caption(
                "This only confirms each cited ID exists - it does not "
                "confirm the draft is factually accurate, or that any "
                "given citation actually supports the claim beside it."
            )

        st.download_button(
            "Download draft as Markdown",
            data=draft.draft_markdown,
            file_name="portfolio_report_draft.md",
            mime="text/markdown",
            disabled=not validation.is_valid,
        )
