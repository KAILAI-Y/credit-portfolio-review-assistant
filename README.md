# Credit Portfolio Review Assistant

## Business question

How do observed next-month default-label rates vary across customer segments, and how does expanding a candidate review scope change workload and historical default coverage?

## Completed analysis

- Data quality checks and portfolio baseline analysis.
- Repayment-status segmentation and credit-limit stratified analysis.
- Candidate review-scope comparison and incremental workload analysis.
- Reconciliation assertions and an English management report.

The notebook's calculations call the shared `core/` modules (`core/metrics.py`,
`core/validator.py`, `core/review_scopes.py`) instead of duplicating the logic
inline, so the notebook and any future application share one implementation.
These modules are covered by the automated tests in `tests/` (run with
`python -m pytest` from the repository root).

| Scope | Clients selected | Positive labels selected | Historical positive-label coverage |
| --- | ---: | ---: | ---: |
| PAY_0 >= 2 | 3,130 | 2,177 | 32.81% |
| PAY_0 > 0 | 6,818 | 3,429 | 51.67% |

Expanding the scope selects 3,688 additional clients and 1,252 additional positive labels. The overall sample contains 30,000 clients and 6,636 positive labels (22.12%).

## Deliverables

- [Analysis notebook](analysis/notebooks/credit-card-portfolio-risk-review.ipynb)
- [Management report](analysis/reports/management-report-en.pdf)

## Data and notebook usage

The full 30,000-client dataset is included in `data/UCI_Credit_Card.csv`, converted from the original [UCI spreadsheet](https://doi.org/10.24432/C55S3H). See [data provenance and CC BY 4.0 attribution](data/README.md) for the conversion details. No Kaggle account or separate data download is needed.

From the repository root (Python 3.11 or newer):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m jupyterlab analysis/notebooks/credit-card-portfolio-risk-review.ipynb
```

On Windows, activate with `.venv\Scripts\activate` instead. Select the environment's Python kernel and use **Restart Kernel and Run All Cells**. The notebook locates the bundled data from the repository root or any subdirectory.

The data describes Taiwanese clients with April–September 2005 history and a next-month outcome label. The PDF is the previously delivered report; refreshed notebook outputs are generated from the bundled CSV.

Verified on 2026-09-12 using Python 3.11 and the pinned dependencies: all 23 code cells executed from a fresh kernel, both charts rendered, and reconciliation checks passed, matching the results before the notebook was refactored to call the shared `core/` modules. The data loader and `core/` imports were checked from both the repository root and the notebook directory.
