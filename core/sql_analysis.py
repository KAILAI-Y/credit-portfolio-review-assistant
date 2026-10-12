"""Independent SQLite calculations and reconciliation with the Python core."""
from pathlib import Path
import math
import sqlite3

import pandas as pd

from .metrics import portfolio_overview, repayment_status_groups, credit_limit_bands, segment_summary, stratified_summary
from .review_scopes import compare_scopes
from .validator import validate_portfolio

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "portfolio.sql"


def sql_analysis(df: pd.DataFrame) -> dict:
    validation = validate_portfolio(df)
    if not validation.is_valid:
        raise ValueError("; ".join(validation.errors))
    selected = df[["ID", "LIMIT_BAL", "PAY_0", "default.payment.next.month"]].copy()
    selected.columns = ["id", "limit_bal", "pay_0", "default_label"]
    with sqlite3.connect(":memory:") as conn:
        selected.to_sql("portfolio", conn, index=False)
        conn.executescript(SQL_PATH.read_text())
        baseline = pd.read_sql_query("SELECT * FROM portfolio_baseline", conn).iloc[0].to_dict()
        repayment = pd.read_sql_query("SELECT * FROM repayment_segments", conn).set_index("pay0_group")
        stratified = pd.read_sql_query("SELECT * FROM stratified_segments", conn).set_index(["pay0_group", "limit_band"])
        scopes = pd.read_sql_query("SELECT * FROM review_summary", conn).set_index("scope")
    return {"baseline": baseline, "repayment": repayment, "stratified": stratified, "scopes": scopes}


def reconciliation_report(df: pd.DataFrame) -> pd.DataFrame:
    """One evidence row per metric; NULL/NaN means undefined, never zero."""
    sql = sql_analysis(df)
    checks = []

    def compare(name, actual, expected):
        undefined = pd.isna(actual) and pd.isna(expected)
        passed = undefined or (not pd.isna(actual) and not pd.isna(expected)
                               and math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12))
        checks.append({"metric": name, "sql_value": actual, "python_value": expected, "passed": bool(passed)})

    for key, value in portfolio_overview(df).items():
        compare(f"baseline.{key}", sql["baseline"][key], value)
    group = repayment_status_groups(df)
    for section, expected in [("repayment", segment_summary(df, group)),
                              ("stratified", stratified_summary(df, [group, credit_limit_bands(df)]))]:
        actual = sql[section].reindex(expected.index)
        for index, row in expected.iterrows():
            for key, value in row.items():
                # SQL omits unobserved combinations; Python may represent empty bands.
                actual_value = actual.loc[index, key]
                if key in ("total_clients", "positive_labels", "portfolio_share", "label_share") and pd.isna(actual_value) and row["total_clients"] == 0:
                    actual_value = 0 if not pd.isna(value) else float("nan")
                compare(f"{section}.{index}.{key}", actual_value, value)
    scopes = compare_scopes(df)
    for scope in ("scope_a", "scope_b", "increment"):
        for key, value in scopes[scope].items():
            sql_key = "positive_label_coverage" if key == "coverage_gain" else key
            compare(f"{scope}.{key}", sql["scopes"].loc[scope, sql_key], value)
    return pd.DataFrame(checks)
