# Business acceptance pack

## Purpose and user scenario
A simulated credit portfolio analyst compares review workload against historical next-month outcome coverage. The analyst validates data, examines repayment/limit segments, compares Scope A and B, verifies independent SQL calculations, and exports evidence for a manager. These results describe historical associations; they are not forecasts or estimates of defaults prevented.

## Field contract
| Source | SQL | Meaning / checks |
|---|---|---|
| ID | id | Numeric, unique, finite, nonmissing client identifier |
| LIMIT_BAL | limit_bal | Numeric finite credit limit in TWD; bands at 50,000, 140,000, 240,000 are right-inclusive |
| PAY_0 | pay_0 | Finite integer recorded repayment code; undocumented codes retained with a warning |
| default.payment.next.month | default_label | Binary historical outcome, 0 or 1; never an input to an actual lending decision |

SQL only receives these four fields. Python validates the input before SQLite calculations. The SQL and Python implementations share definitions, but calculate results independently.

## Traceability and acceptance scenarios
| ID | Requirement | Scenario and expected result | Evidence |
|---|---|---|---|
| AC-01 | FR-01 | Missing fields, duplicate/missing IDs, nonfinite numbers or invalid outcome block analysis | tests/test_validator.py; tests/test_sql_analysis.py |
| AC-02 | FR-02 | Bundled data: 30,000 clients, 6,636 positive labels, rate 22.12% | SQL reconciliation CSV; tests/test_metrics.py |
| AC-03 | FR-03 | A: 3,130/2,177; B: 6,818/3,429 clients/positive labels | tests/test_review_scopes.py; SQL reconciliation CSV |
| AC-04 | FR-03 | Expansion adds 3,688 clients and 1,252 positive labels; counts reconcile | tests/test_review_scopes.py; SQL reconciliation CSV |
| AC-05 | FR-06 | Baseline, segment and scope results agree with Python; rate tolerance 1e-12 | tests/test_sql_analysis.py; SQL reconciliation CSV |
| AC-06 | FR-06 | Credit-limit boundaries and empty scopes; zero positive labels yield undefined coverage | tests/test_sql_analysis.py |
| AC-07 | FR-06 | Click Verify SQL/Python metrics; see pass/fail and downloadable metric evidence without API key | tests/test_app_main.py SQL verification scenario |

## Manual walkthrough (not bank sign-off)
1. Start `streamlit run app/main.py` without API credentials.
2. Review code warnings; verify the baseline and repayment/limit summaries.
3. Compare Scope A and B. Explain the extra workload and historical coverage gain.
4. Click Verify SQL/Python metrics and download the reconciliation evidence.
5. Check undefined-rate presentation and the historical-data limitations before reporting.

Status: automated evidence is recorded by the local verification run. Manual stakeholder acceptance is pending; no external business user or bank has approved this application. Actual AI evaluations and factual checks remain separate from this offline acceptance pack.

## Change rationale and exclusions
This enhancement adds a SQL calculation path and traceable evidence, preserving historical definitions and the existing AI report feature. Corporate facilities, covenants, credit approval, user permissions and persistent case management remain future work, not implemented capabilities.
