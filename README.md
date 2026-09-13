# Credit Portfolio Review Assistant

Independent historical credit-card portfolio analysis by Kailai Yang, with an AI reporting assistant planned as a subsequent extension.

## Business question

How do observed next-month default-label rates vary across customer segments, and how does expanding a candidate review scope change workload and historical default coverage?

## Completed analysis

- Data quality checks and portfolio baseline analysis.
- Repayment-status segmentation and credit-limit stratified analysis.
- Candidate review-scope comparison and incremental workload analysis.
- Reconciliation assertions and management reports in English and Chinese.

| Scope | Clients selected | Positive labels selected | Historical positive-label coverage |
| --- | ---: | ---: | ---: |
| PAY_0 >= 2 | 3,130 | 2,177 | 32.81% |
| PAY_0 > 0 | 6,818 | 3,429 | 51.67% |

Expanding the scope selects 3,688 additional clients and 1,252 additional positive labels. The overall sample contains 30,000 clients and 6,636 positive labels (22.12%).

## Deliverables

- [English analysis notebook](analysis/notebooks/credit-card-portfolio-risk-review.ipynb)
- [English management report](analysis/reports/management-report-en.pdf)
- [Chinese management report](analysis/reports/management-report-zh.pdf)

## Data and notebook usage

Source: [UCI Default of Credit Card Clients](https://doi.org/10.24432/C55S3H), available on [Kaggle](https://www.kaggle.com/datasets/uciml/default-of-credit-card-clients-dataset).

The data describes Taiwanese clients with April–September 2005 history and a next-month outcome label. Raw data is not included in this repository. Open the notebook on Kaggle with the linked dataset attached, verify its input path, and run all cells from a fresh session. For local use, download the source CSV and update the loading cell; the notebook uses Python, pandas, NumPy, Matplotlib, and IPython/Jupyter.

This initial repository preserves the supplied notebook and existing reports. The notebook contains saved outputs and reconciliation checks; it has not been freshly executed as part of repository setup. The reports are retained as previously delivered snapshots, including any verification notes. The notebook title still contains its original last-updated placeholder.

## Planned extension — not yet implemented

- Shared Python calculation modules used by the notebook and application.
- A simple interface for portfolio metrics and scope comparisons.
- Claude-generated report drafts grounded in calculated summaries.
- Calculation tests and AI-response evaluations with source references.

## Limitations

This is an independent historical-data project, not bank employment or a deployed banking system. Observed associations do not establish causation, intervention effectiveness, or losses prevented. Candidate scopes require validation on recent independent data before operational use. Repayment-code interpretation and outcome definitions have documented limitations. No predictive model was trained.
