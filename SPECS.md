# Business Requirements: Credit Portfolio Review Assistant

## 1. Background and Business Problem

Reviewing a credit card portfolio requires analysts to validate data, compare customer segments, and explain the implications of different customer-review scopes.

This project turns an existing historical portfolio analysis into a reusable application that presents calculated metrics and generates management-report drafts grounded in those results.

## 2. Target User

A credit risk analyst preparing a portfolio review for a manager. This is a simulated workflow using public historical data, rather than a system commissioned or deployed by a bank.

## 3. Business Questions

1. How do observed next-month default-label rates vary across repayment-status and credit-limit segments?
2. How do two candidate customer-review scopes compare in workload and historical default-label coverage?
3. What findings, trade-offs, and limitations should be included in a management-report draft?

## 4. Inputs and Metric Definitions

The first version uses the existing 30,000-client historical dataset.

Required analysis fields:
- `ID`: client identifier.
- `LIMIT_BAL`: credit limit.
- `PAY_0`: recorded September repayment-status code.
- `default.payment.next.month`: next-month binary outcome label.

Core metrics:
- Observed default-label rate: positive labels divided by clients in the selected population.
- Workload share: selected clients divided by all clients.
- Positive-label coverage: selected positive labels divided by all positive labels.

Candidate scopes:
- Scope A: `PAY_0 >= 2`.
- Scope B: `PAY_0 > 0`.

These are exploratory rules, not approved bank policies. Retain the existing notebook's segment definitions and credit-limit boundaries. An undefined rate, such as coverage when there are no positive labels, must be displayed as unavailable rather than zero.

## 5. Functional Requirements

### FR-01 — Data validation
Check required fields, missing values, unique client identifiers, numeric analysis fields, and valid binary outcome labels. Display validation issues and block analysis when required checks fail. Flag undocumented repayment-code meanings without inventing interpretations.

### FR-02 — Portfolio overview
Display client counts, positive-label counts, the overall label rate, repayment-status and credit-limit segment summaries, and comparisons within repayment-status groups.

### FR-03 — Review-scope comparison
Display selected clients, workload share, positive-label coverage, and observed label rate for each scope. Show the incremental population, positive labels, and coverage when moving from Scope A to Scope B.

### FR-04 — AI report generation
Generate a management-report draft using calculated summary tables and documented metric definitions. Reference the table or metric supporting each quantitative finding. Explain missing information for unsupported questions rather than inventing results.

### FR-05 — Report review and export
Allow the analyst to review and download the generated draft as Markdown. Clearly label the output as requiring human review.

## 5.1 Architecture Mapping

These are planned implementation paths, not existing features.

- FR-01: `core/validator.py`.
- FR-02: `core/metrics.py`.
- FR-03: `core/review_scopes.py`, reusing shared metric definitions.
- FR-04: `app/assistant.py` (Claude API client and source-grounded prompt templates).
- FR-05: `app/main.py` (Streamlit UI and Markdown export).
- Section 7, deterministic checks: `tests/test_validator.py`, `tests/test_metrics.py`, and `tests/test_review_scopes.py` (pytest).
- Section 7, model-response checks: `evals/questions.json` and `evals/results.md` (actual API evaluation cases and recorded outcomes).

## 6. Reliability Requirements

- Python calculates all portfolio metrics; the AI explains supplied results rather than independently calculating core metrics.
- Notebook and application use shared calculation functions.
- Unsupported questions receive a clear explanation of what information is missing.
- API failures produce a visible error rather than a fabricated report.
- API credentials are not stored in source control.
- Only necessary aggregate summaries are sent to the model.
- Statistical associations must not be presented as causal effects or validated intervention outcomes.

## 7. Acceptance Criteria

- A fresh run on the full dataset returns 30,000 clients, 6,636 positive labels, and an overall label rate of 22.12%.
- Scope A selects 3,130 clients and 2,177 positive labels.
- Scope B selects 6,818 clients and 3,429 positive labels.
- The incremental population contains 3,688 clients and 1,252 positive labels.
- All segmentation totals reconcile with the overall population.
- Missing required fields, duplicate IDs, and invalid labels produce clear errors.
- Undefined rates do not cause crashes or silently become zero.
- Quantitative statements in evaluated report drafts match their referenced calculation results.
- Evaluated responses do not claim that changing credit limits causes lower defaults or that customer reviews prevent losses.
- A user can generate and download a report draft through the interface.

Counts are checked exactly. Rates are checked using unrounded values with an appropriate numerical tolerance. Record model identifier, evaluation date, and prompt version with AI evaluation results; passing a finite evaluation set does not guarantee all future answers.

## 8. Out of Scope for Version 1

- Arbitrary dataset uploads and unrestricted chat.
- Predictive credit scoring or model training.
- Automated lending, credit-limit, or collections decisions.
- Estimates of losses prevented or intervention effectiveness.
- Production deployment, user accounts, and regulatory compliance assessment.
