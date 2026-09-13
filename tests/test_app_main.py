"""Streamlit AppTest for app/main.py.

Verifies the repayment-status summary table against the shared
core/metrics.py calculations, without duplicating them.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import dotenv
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app.assistant as assistant_module
from app.assistant import ReportDraft, ReportGenerationError
from core.metrics import (
    LIMIT_BAND_LABELS,
    credit_limit_bands,
    portfolio_overview,
    repayment_status_groups,
    segment_summary,
    stratified_summary,
)
from core.review_scopes import SCOPE_A_LABEL, SCOPE_B_LABEL, compare_scopes

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "app" / "main.py"
DATA_PATH = REPO_ROOT / "data" / "UCI_Credit_Card.csv"

# Captured before the autouse fixture below ever patches dotenv.load_dotenv,
# so tests that need the real parsing/override behavior (against a temp
# file, never the real .env) can still reach it.
_REAL_LOAD_DOTENV = dotenv.load_dotenv


@pytest.fixture(autouse=True)
def _default_report_env(monkeypatch):
    """Deterministic default: AI report drafting looks unconfigured, and no
    test ever reads the real repository .env file, unless a test explicitly
    sets env vars or re-patches ``dotenv.load_dotenv`` itself."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)

GROUP_ORDER = ["PAY_0 <= 0", "PAY_0 = 1", "PAY_0 >= 2"]

# app/main.py renames "> 240,000" for display only (st.table renders a
# leading ">" as a Markdown blockquote). Mirrored here so tests can check
# the rendered label while still keying into shared-calculation results by
# the real, underlying category.
CREDIT_LIMIT_BAND_DISPLAY_LABELS = {"> 240,000": "Above 240,000"}


def _display_band_label(label: str) -> str:
    return CREDIT_LIMIT_BAND_DISPLAY_LABELS.get(label, label)


DISPLAY_LIMIT_BAND_LABELS = [_display_band_label(band) for band in LIMIT_BAND_LABELS]


def test_repayment_status_table_matches_shared_calculations():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception

    full_dataset = pd.read_csv(DATA_PATH)
    expected_overview = portfolio_overview(full_dataset)
    expected_summary = segment_summary(
        full_dataset, repayment_status_groups(full_dataset)
    ).reindex(GROUP_ORDER)

    # Overview metrics (added previously) should still reconcile with core.
    assert at.metric[0].value == f"{expected_overview['total_clients']:,}"
    assert at.metric[1].value == f"{expected_overview['positive_labels']:,}"
    assert at.metric[2].value == f"{expected_overview['label_rate']:.2%}"

    # Four tables now: repayment-status summary, credit-limit summary,
    # stratified summary, then the review-scope comparison.
    assert len(at.table) == 4
    table = at.table[0].value

    # Group order.
    assert list(table.index) == GROUP_ORDER

    # Counts and rates match segment_summary() exactly, formatted for display.
    # Cells are indexed individually (not via a whole-row .loc[group]) so a
    # mixed-dtype row doesn't get silently upcast to float before comparison.
    for group in GROUP_ORDER:
        assert table.loc[group, "Total clients"] == (
            f"{expected_summary.loc[group, 'total_clients']:,}"
        )
        assert table.loc[group, "Positive-label count"] == (
            f"{expected_summary.loc[group, 'positive_labels']:,}"
        )
        assert table.loc[group, "Observed default-label rate"] == (
            f"{expected_summary.loc[group, 'label_rate']:.2%}"
        )
        assert table.loc[group, "Portfolio share"] == (
            f"{expected_summary.loc[group, 'portfolio_share']:.2%}"
        )
        assert table.loc[group, "Positive-label coverage"] == (
            f"{expected_summary.loc[group, 'label_share']:.2%}"
        )

    # Group-level totals reconcile with the overall portfolio.
    assert expected_summary["total_clients"].sum() == expected_overview["total_clients"]
    assert (
        expected_summary["positive_labels"].sum() == expected_overview["positive_labels"]
    )


# Reference values for the bundled dataset - test expectations only, never
# hardcoded into the app's own display logic.
EXPECTED_LIMIT_BAND_CLIENTS = {
    "<= 50,000": 7676,
    "50,000-140,000": 7614,
    "140,000-240,000": 7643,
    "> 240,000": 7067,
}
EXPECTED_LIMIT_BAND_POSITIVES = {
    "<= 50,000": 2440,
    "50,000-140,000": 1882,
    "140,000-240,000": 1326,
    "> 240,000": 988,
}
EXPECTED_LIMIT_BAND_RATES = {
    "<= 50,000": 0.3179,
    "50,000-140,000": 0.2472,
    "140,000-240,000": 0.1735,
    "> 240,000": 0.1398,
}


def test_credit_limit_table_matches_shared_calculations():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception

    full_dataset = pd.read_csv(DATA_PATH)
    expected_overview = portfolio_overview(full_dataset)
    expected_summary = segment_summary(
        full_dataset, credit_limit_bands(full_dataset)
    ).reindex(LIMIT_BAND_LABELS)

    # Four tables now: repayment-status summary, credit-limit summary,
    # stratified summary, then the review-scope comparison.
    assert len(at.table) == 4
    table = at.table[1].value

    # Band order, using the rendered (display) labels - "> 240,000" is
    # rewritten to "Above 240,000" to avoid Markdown blockquote rendering.
    assert list(table.index) == DISPLAY_LIMIT_BAND_LABELS

    # Counts and rates match segment_summary() exactly, formatted for display.
    # `band` (from core.metrics) keys the underlying calculation results;
    # `display_band` is only used to locate the row in the rendered table.
    for band in LIMIT_BAND_LABELS:
        display_band = _display_band_label(band)
        assert table.loc[display_band, "Total clients"] == (
            f"{expected_summary.loc[band, 'total_clients']:,}"
        )
        assert table.loc[display_band, "Positive-label count"] == (
            f"{expected_summary.loc[band, 'positive_labels']:,}"
        )
        assert table.loc[display_band, "Observed default-label rate"] == (
            f"{expected_summary.loc[band, 'label_rate']:.2%}"
        )
        assert table.loc[display_band, "Portfolio share"] == (
            f"{expected_summary.loc[band, 'portfolio_share']:.2%}"
        )
        assert table.loc[display_band, "Positive-label coverage"] == (
            f"{expected_summary.loc[band, 'label_share']:.2%}"
        )

    # Cross-check the shared calculation against the documented reference
    # values for the bundled dataset (test expectations, not display values).
    for band in LIMIT_BAND_LABELS:
        assert expected_summary.loc[band, "total_clients"] == EXPECTED_LIMIT_BAND_CLIENTS[band]
        assert (
            expected_summary.loc[band, "positive_labels"]
            == EXPECTED_LIMIT_BAND_POSITIVES[band]
        )
        assert expected_summary.loc[band, "label_rate"] == pytest.approx(
            EXPECTED_LIMIT_BAND_RATES[band], abs=5e-5
        )

    # Band-level totals reconcile with the overall portfolio.
    assert expected_summary["total_clients"].sum() == expected_overview["total_clients"]
    assert (
        expected_summary["positive_labels"].sum() == expected_overview["positive_labels"]
    )


STRATIFIED_ORDER = [
    (status, band) for status in GROUP_ORDER for band in LIMIT_BAND_LABELS
]

# Portfolio-wide totals for the bundled dataset - test expectations only,
# never hardcoded into the app's own display logic.
EXPECTED_TOTAL_CLIENTS = 30000
EXPECTED_TOTAL_POSITIVE_LABELS = 6636


def test_stratified_table_matches_shared_calculations():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception

    full_dataset = pd.read_csv(DATA_PATH)
    expected_stratified = stratified_summary(
        full_dataset,
        [repayment_status_groups(full_dataset), credit_limit_bands(full_dataset)],
    ).reindex(STRATIFIED_ORDER)

    # Four tables now: repayment-status summary, credit-limit summary,
    # stratified summary, then the review-scope comparison.
    assert len(at.table) == 4
    table = at.table[2].value

    # 12 combinations, in the required order: status outer, band inner.
    # The "Credit-limit band" column uses the rendered (display) label for
    # "> 240,000"; the underlying category is still used to key the
    # shared-calculation results below.
    display_stratified_order = [
        (status, _display_band_label(band)) for status, band in STRATIFIED_ORDER
    ]
    assert len(table) == 12
    assert list(zip(table["Repayment-status group"], table["Credit-limit band"])) == (
        display_stratified_order
    )

    # Counts and rates match stratified_summary() exactly, formatted for display.
    for row_index, (status, band) in enumerate(STRATIFIED_ORDER):
        row = table.iloc[row_index]
        assert row["Total clients"] == (
            f"{expected_stratified.loc[(status, band), 'total_clients']:,}"
        )
        assert row["Positive-label count"] == (
            f"{expected_stratified.loc[(status, band), 'positive_labels']:,}"
        )
        assert row["Observed default-label rate"] == (
            f"{expected_stratified.loc[(status, band), 'label_rate']:.2%}"
        )

    # Portfolio-wide totals - test expectations, not hardcoded display values.
    assert expected_stratified["total_clients"].sum() == EXPECTED_TOTAL_CLIENTS
    assert expected_stratified["positive_labels"].sum() == EXPECTED_TOTAL_POSITIVE_LABELS


SCOPE_ORDER = [SCOPE_A_LABEL, SCOPE_B_LABEL]

# Reference values for the bundled dataset - test expectations only, never
# hardcoded into the app's own display logic.
EXPECTED_SCOPE_CLIENTS = {
    SCOPE_A_LABEL: 3130,
    SCOPE_B_LABEL: 6818,
}
EXPECTED_SCOPE_POSITIVES = {
    SCOPE_A_LABEL: 2177,
    SCOPE_B_LABEL: 3429,
}


def test_review_scope_table_matches_shared_calculations():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception

    full_dataset = pd.read_csv(DATA_PATH)
    expected_comparison = compare_scopes(full_dataset)
    expected_rows = {
        SCOPE_A_LABEL: expected_comparison["scope_a"],
        SCOPE_B_LABEL: expected_comparison["scope_b"],
    }

    # Four tables now: repayment-status summary, credit-limit summary,
    # stratified summary, then the review-scope comparison.
    assert len(at.table) == 4
    table = at.table[3].value

    # Row order: Scope A, then Scope B.
    assert list(table.index) == SCOPE_ORDER

    # Counts and rates match compare_scopes() exactly, formatted for display.
    for scope in SCOPE_ORDER:
        expected = expected_rows[scope]
        assert table.loc[scope, "Clients selected"] == f"{expected['clients']:,}"
        assert table.loc[scope, "Workload share"] == f"{expected['workload_share']:.2%}"
        assert table.loc[scope, "Positive-label count"] == (
            f"{expected['positive_labels']:,}"
        )
        assert table.loc[scope, "Positive-label coverage"] == (
            f"{expected['positive_label_coverage']:.2%}"
        )
        assert table.loc[scope, "Observed default-label rate"] == (
            f"{expected['label_rate']:.2%}"
        )

    # Cross-check against the documented reference values for the bundled
    # dataset (test expectations, not display values).
    for scope in SCOPE_ORDER:
        assert expected_rows[scope]["clients"] == EXPECTED_SCOPE_CLIENTS[scope]
        assert expected_rows[scope]["positive_labels"] == EXPECTED_SCOPE_POSITIVES[scope]


# Reference values for the bundled dataset - test expectations only, never
# hardcoded into the app's own display logic.
EXPECTED_INCREMENT_CLIENTS = 3688
EXPECTED_INCREMENT_POSITIVES = 1252


def test_incremental_metrics_match_shared_calculations():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception

    full_dataset = pd.read_csv(DATA_PATH)
    expected_increment = compare_scopes(full_dataset)["increment"]

    # Still four tables - the incremental section uses st.metric, not st.table.
    assert len(at.table) == 4

    # The three overview metrics stay first; the four incremental metrics
    # are appended after them, in the order they're written in the script.
    assert len(at.metric) == 7
    increment_metrics = {m.label: m.value for m in at.metric[3:]}

    assert increment_metrics["Additional clients to review"] == (
        f"{expected_increment['clients']:,}"
    )
    assert increment_metrics["Additional positive labels"] == (
        f"{expected_increment['positive_labels']:,}"
    )
    assert increment_metrics["Observed label rate among additional clients"] == (
        f"{expected_increment['label_rate']:.2%}"
    )
    assert increment_metrics["Positive-label coverage gain"] == (
        f"{expected_increment['coverage_gain'] * 100:.2f} pp"
    )

    # Cross-check against the documented reference values for the bundled
    # dataset (test expectations, not display values).
    assert expected_increment["clients"] == EXPECTED_INCREMENT_CLIENTS
    assert expected_increment["positive_labels"] == EXPECTED_INCREMENT_POSITIVES


# --- AI report draft (FR-04) UI ----------------------------------------------
#
# The backend (app/assistant.generate_report_draft) is always mocked here:
# these tests verify the UI's call discipline and display logic, not the
# real model's output (see tests/test_assistant.py for that boundary).

FAKE_MODEL = "claude-opus-5"
FAKE_API_KEY = "sk-ant-api03-not-a-real-key-0000000000000000000000"


def _fake_draft(markdown="## Executive Summary\nBody (source: portfolio_overview)."):
    return ReportDraft(
        draft_markdown=markdown,
        model=FAKE_MODEL,
        requested_model=FAKE_MODEL,
        prompt_version=assistant_module.PROMPT_VERSION,
        input_tokens=100,
        output_tokens=50,
        stop_reason="end_turn",
    )


def test_report_draft_shows_safe_message_when_not_configured():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception
    assert len(at.button) == 0
    assert any("not configured" in info.value.lower() for info in at.info)
    assert FAKE_API_KEY not in at.get("info")[0].value


def test_initial_load_makes_zero_report_generation_calls(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)
    mock_generate = MagicMock()
    monkeypatch.setattr(assistant_module, "generate_report_draft", mock_generate)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception
    mock_generate.assert_not_called()
    assert len(at.button) == 1
    assert len(at.markdown) == 0
    assert len(at.download_button) == 0


def test_one_click_generates_one_call_and_shows_draft(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)
    mock_generate = MagicMock(return_value=_fake_draft())
    monkeypatch.setattr(assistant_module, "generate_report_draft", mock_generate)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    at.button[0].click().run(timeout=30)

    assert not at.exception
    mock_generate.assert_called_once()
    assert any("generated" in s.value.lower() for s in at.success)
    assert any("Executive Summary" in md.value for md in at.markdown)
    assert any(FAKE_MODEL in c.value for c in at.caption)
    assert any(assistant_module.PROMPT_VERSION in c.value for c in at.caption)
    assert len(at.download_button) == 1


def test_rerun_preserves_draft_without_another_call_or_stale_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)
    mock_generate = MagicMock(return_value=_fake_draft())
    monkeypatch.setattr(assistant_module, "generate_report_draft", mock_generate)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    at.button[0].click().run(timeout=30)
    assert mock_generate.call_count == 1

    # A later rerun not caused by clicking "Generate report draft" again
    # (e.g. the download button, or any other widget) must not call the
    # backend again, and must not relabel the old draft as a fresh success.
    at.run(timeout=30)

    assert not at.exception
    mock_generate.assert_called_once()
    assert any("Executive Summary" in md.value for md in at.markdown)
    assert len(at.success) == 0


def test_generation_failure_displays_safe_error_and_no_draft(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)
    mock_generate = MagicMock(
        side_effect=ReportGenerationError("Report generation failed: rate limited.")
    )
    monkeypatch.setattr(assistant_module, "generate_report_draft", mock_generate)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    at.button[0].click().run(timeout=30)

    assert not at.exception
    mock_generate.assert_called_once()
    assert any("rate limited" in e.value.lower() for e in at.error)
    assert len(at.markdown) == 0
    assert len(at.download_button) == 0
    assert len(at.success) == 0


def test_failure_after_a_prior_success_keeps_old_draft_without_new_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)
    mock_generate = MagicMock(return_value=_fake_draft())
    monkeypatch.setattr(assistant_module, "generate_report_draft", mock_generate)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    at.button[0].click().run(timeout=30)
    assert any("Executive Summary" in md.value for md in at.markdown)

    mock_generate.side_effect = ReportGenerationError(
        "Report generation failed: rate limited."
    )
    at.button[0].click().run(timeout=30)

    assert not at.exception
    assert mock_generate.call_count == 2
    assert any("rate limited" in e.value.lower() for e in at.error)
    # The previously generated draft is still shown, but not mislabeled as
    # a fresh success.
    assert any("Executive Summary" in md.value for md in at.markdown)
    assert len(at.success) == 0


# --- .env loading -------------------------------------------------------------
#
# The autouse _default_report_env fixture replaces dotenv.load_dotenv with a
# no-op by default, so every other test in this file is isolated from the
# real repository .env file. These tests re-patch it themselves to verify
# app/main.py's own loading behavior, always against a temporary file with
# fake values - never the real .env.


def _redirect_load_dotenv(monkeypatch, fake_env_path):
    """Route app/main.py's dotenv.load_dotenv(REPO_ROOT / ".env", ...) call
    to ``fake_env_path`` instead, while still exercising the real
    python-dotenv parsing/override behavior (not a fake stand-in)."""

    def _redirected(_path, **kwargs):
        return _REAL_LOAD_DOTENV(fake_env_path, **kwargs)

    monkeypatch.setattr(dotenv, "load_dotenv", _redirected)


def test_config_loaded_from_dotenv_file_when_unset(monkeypatch, tmp_path):
    fake_env_path = tmp_path / ".env"
    fake_env_path.write_text(
        "ANTHROPIC_API_KEY=fake-key-from-dotenv\n"
        "ANTHROPIC_MODEL=fake-model-from-dotenv\n"
    )
    _redirect_load_dotenv(monkeypatch, fake_env_path)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception
    assert len(at.button) == 1  # now configured: button is shown
    assert not any(
        "not configured" in info.value.lower() for info in at.info
    )
    # The loaded values are used, but never rendered anywhere on the page.
    page_text = "".join(i.value for i in at.info) + "".join(
        c.value for c in at.caption
    )
    assert "fake-key-from-dotenv" not in page_text
    assert "fake-model-from-dotenv" not in page_text


def test_existing_env_vars_are_not_overridden_by_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real-shell-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "real-shell-model")

    fake_env_path = tmp_path / ".env"
    fake_env_path.write_text(
        "ANTHROPIC_API_KEY=dotenv-key\nANTHROPIC_MODEL=dotenv-model\n"
    )
    _redirect_load_dotenv(monkeypatch, fake_env_path)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception
    assert len(at.button) == 1
    # The pre-set (shell) values win; override=False must not let the
    # .env file's values replace them.
    assert os.environ["ANTHROPIC_API_KEY"] == "real-shell-key"
    assert os.environ["ANTHROPIC_MODEL"] == "real-shell-model"


def test_initial_page_load_still_makes_zero_api_calls_with_dotenv_configured(
    monkeypatch, tmp_path
):
    fake_env_path = tmp_path / ".env"
    fake_env_path.write_text(
        "ANTHROPIC_API_KEY=fake-key-from-dotenv\n"
        "ANTHROPIC_MODEL=fake-model-from-dotenv\n"
    )
    _redirect_load_dotenv(monkeypatch, fake_env_path)
    mock_generate = MagicMock()
    monkeypatch.setattr(assistant_module, "generate_report_draft", mock_generate)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)

    assert not at.exception
    mock_generate.assert_not_called()
    assert len(at.button) == 1
    assert len(at.markdown) == 0
    assert len(at.download_button) == 0
    assert len(at.success) == 0
