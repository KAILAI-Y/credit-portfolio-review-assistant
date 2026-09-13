import pandas as pd

from core.validator import REQUIRED_COLUMNS, validate_portfolio


def make_df(**overrides):
    base = {
        "ID": [1, 2, 3, 4],
        "LIMIT_BAL": [20000, 50000, 140000, 240000],
        "PAY_0": [-1, 0, 1, 2],
        "default.payment.next.month": [0, 1, 0, 1],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_valid_dataset_has_no_errors():
    result = validate_portfolio(make_df())

    assert result.is_valid
    assert result.errors == []


def test_missing_required_column_is_an_error():
    df = make_df().drop(columns=["LIMIT_BAL"])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any("LIMIT_BAL" in message for message in result.errors)


def test_all_missing_columns_are_reported():
    df = pd.DataFrame({"ID": [1, 2]})

    result = validate_portfolio(df)

    assert not result.is_valid
    error_text = " ".join(result.errors)
    for col in REQUIRED_COLUMNS:
        if col == "ID":
            continue
        assert col in error_text


def test_duplicate_ids_are_an_error():
    df = make_df(ID=[1, 1, 3, 4])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any("duplicate" in message.lower() for message in result.errors)


def test_missing_id_is_an_error():
    df = make_df(ID=[1, None, 3, 4])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any("ID" in message and "missing" in message.lower() for message in result.errors)


def test_missing_values_in_analysis_fields_are_an_error():
    df = make_df(LIMIT_BAL=[20000, None, 140000, 240000])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any("LIMIT_BAL" in message and "missing" in message.lower() for message in result.errors)


def test_non_binary_label_is_an_error():
    df = make_df(**{"default.payment.next.month": [0, 1, 2, 0]})

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any("default.payment.next.month" in message for message in result.errors)


def test_non_numeric_analysis_field_is_an_error():
    df = make_df(LIMIT_BAL=["a", "b", "c", "d"])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any("LIMIT_BAL" in message and "numeric" in message.lower() for message in result.errors)


def test_empty_input_is_an_error():
    df = pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any("empty" in message.lower() for message in result.errors)


def test_undocumented_pay0_codes_are_warnings_not_errors():
    df = make_df(PAY_0=[-2, 0, 1, 2])

    result = validate_portfolio(df)

    assert result.is_valid
    assert result.errors == []
    assert result.warnings, "expected a warning about undocumented PAY_0 codes"
    assert result.undocumented_pay0_codes == {-2: 1, 0: 1}


def test_documented_pay0_codes_produce_no_warning():
    df = make_df(PAY_0=[-1, 1, 2, 9])

    result = validate_portfolio(df)

    assert result.is_valid
    assert result.warnings == []
    assert result.undocumented_pay0_codes == {}


def test_non_finite_analysis_value_is_an_error():
    df = make_df(LIMIT_BAL=[20000, 50000, float("inf"), 240000])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any(
        "LIMIT_BAL" in message and "finite" in message.lower()
        for message in result.errors
    )


def test_negative_infinite_value_is_an_error():
    df = make_df(PAY_0=[-1, 0, float("-inf"), 2])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any(
        "PAY_0" in message and "finite" in message.lower()
        for message in result.errors
    )


def test_non_integer_pay0_value_is_an_error():
    df = make_df(PAY_0=[-1, 0, 1.5, 2])

    result = validate_portfolio(df)

    assert not result.is_valid
    assert any(
        "PAY_0" in message and "integer" in message.lower()
        for message in result.errors
    )


def test_non_integer_pay0_value_does_not_crash_finite_check():
    # A non-integer value must not be misreported as non-finite.
    df = make_df(PAY_0=[-1, 0, 1.5, 2])

    result = validate_portfolio(df)

    assert not any("finite" in message.lower() for message in result.errors)


def test_undocumented_integer_codes_still_warn_when_a_non_integer_value_is_present():
    df = make_df(PAY_0=[-2, 0, 1.5, 2])

    result = validate_portfolio(df)

    # The non-integer 1.5 is a blocking error...
    assert not result.is_valid
    assert any("integer" in message.lower() for message in result.errors)

    # ...but -2 and 0 are still separately flagged as undocumented, valid
    # integer codes, without inventing a meaning for either.
    assert result.undocumented_pay0_codes == {-2: 1, 0: 1}


def test_full_dataset_passes_required_checks_with_documented_undocumented_codes(full_dataset):
    result = validate_portfolio(full_dataset)

    assert result.is_valid, result.errors
    # The source description does not document PAY_0 codes 0 and -2;
    # the notebook (Section 2.5) observes both codes in the full data.
    assert 0 in result.undocumented_pay0_codes
    assert -2 in result.undocumented_pay0_codes
    assert result.warnings
