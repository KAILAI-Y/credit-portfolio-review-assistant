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

The full 30,000-client dataset is included in `data/UCI_Credit_Card.csv.

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

## Claude API configuration

Report generation (see `SPECS.md` FR-04) calls Claude through the official
`anthropic` Python SDK, included in `requirements.txt` alongside
`python-dotenv` for explicit `.env` loading.

### Setup

1. Copy the example environment file (never commit `.env`; it is already
   listed in `.gitignore`):

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set:
   - `ANTHROPIC_API_KEY` — your Anthropic API key.
   - `ANTHROPIC_MODEL` — the model ID to use (for example `claude-opus-5`).

### Verify connectivity

With the virtual environment active and dependencies installed, run:

```bash
python scripts/check_claude_api.py
```

The script loads `.env`, sends one short synthetic prompt with a small
output-token limit, and prints a concise success or failure message. It
never prints the API key or any other credential value. A missing or
invalid key or model produces a clear error instead of a silent failure or
an unnecessary API call.
