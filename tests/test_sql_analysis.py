import pandas as pd
import pytest
from core.sql_analysis import sql_analysis, reconciliation_report


def test_full_dataset_reconciles(full_dataset):
    report = reconciliation_report(full_dataset)
    assert report.passed.all(), report.loc[~report.passed].to_dict("records")
    result = sql_analysis(full_dataset)
    assert result["baseline"]["total_clients"] == 30000
    assert result["scopes"].loc["increment", "clients"] == 3688


@pytest.mark.parametrize("labels", [[0, 0, 0, 0, 0, 0], [1, 0, 1, 0, 1, 0]])
def test_boundaries_and_empty_scopes(labels):
    df = pd.DataFrame({"ID": range(6), "LIMIT_BAL": [50000, 50001, 140000, 140001, 240000, 240001],
                       "PAY_0": [-2, -1, 0, -2, 0, -1], "default.payment.next.month": labels})
    assert reconciliation_report(df).passed.all()
    result = sql_analysis(df)
    assert result["scopes"].loc["scope_a", "clients"] == 0
    assert pd.isna(result["scopes"].loc["scope_a", "label_rate"])


@pytest.mark.parametrize("field,value", [("PAY_0", 1.5), ("ID", None), ("default.payment.next.month", 2)])
def test_invalid_input_blocked(field, value):
    df = pd.DataFrame({"ID": [1], "LIMIT_BAL": [50000], "PAY_0": [1], "default.payment.next.month": [0]})
    df[field] = value
    with pytest.raises(ValueError):
        sql_analysis(df)
