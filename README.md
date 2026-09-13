# Credit Portfolio Review Assistant

## Business question

How do observed next-month default-label rates vary across customer segments, and how does expanding a candidate review scope change workload and historical default coverage?

## Completed analysis

- Data quality checks and portfolio baseline analysis.
- Repayment-status segmentation and credit-limit stratified analysis.
- Candidate review-scope comparison and incremental workload analysis.
- Reconciliation assertions and an English management report.

| Scope | Clients selected | Positive labels selected | Historical positive-label coverage |
| --- | ---: | ---: | ---: |
| PAY_0 >= 2 | 3,130 | 2,177 | 32.81% |
| PAY_0 > 0 | 6,818 | 3,429 | 51.67% |

Expanding the scope selects 3,688 additional clients and 1,252 additional positive labels. The overall sample contains 30,000 clients and 6,636 positive labels (22.12%).

## Deliverables

- [Analysis notebook](analysis/notebooks/credit-card-portfolio-risk-review.ipynb)
- [Management report](analysis/reports/management-report-en.pdf)

## Data and notebook usage

Source: [UCI Default of Credit Card Clients](https://doi.org/10.24432/C55S3H), available on [Kaggle](https://www.kaggle.com/datasets/uciml/default-of-credit-card-clients-dataset).

The data describes Taiwanese clients with April–September 2005 history and a next-month outcome label. Raw data is not included in this repository. Open the notebook on Kaggle with the linked dataset attached, verify its input path, and run all cells from a fresh session. For local use, download the source CSV and update the loading cell; the notebook uses Python, pandas, NumPy, Matplotlib, and IPython/Jupyter.

