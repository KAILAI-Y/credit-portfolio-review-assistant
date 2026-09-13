from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "data" / "UCI_Credit_Card.csv"


@pytest.fixture(scope="session")
def full_dataset() -> pd.DataFrame:
    """The bundled, unmodified 30,000-client dataset."""
    return pd.read_csv(DATA_PATH)
