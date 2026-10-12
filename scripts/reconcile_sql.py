"""Run offline SQL/Python reconciliation and write reproducible evidence."""
import argparse
from pathlib import Path
import sys
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from core.sql_analysis import reconciliation_report, sql_analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/UCI_Credit_Card.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "analysis/reports/sql-reconciliation.csv")
    args = parser.parse_args()
    df = pd.read_csv(args.data)
    report = reconciliation_report(df)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.output, index=False)
    summary = {"dataset_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
               "checks": len(report), "passed": int(report.passed.sum()),
               "baseline": sql_analysis(df)["baseline"]}
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"SQL/Python reconciliation: {summary['passed']}/{summary['checks']} passed")
    return 0 if report.passed.all() else 1


if __name__ == "__main__":
    raise SystemExit(main())
