# Dataset provenance

`UCI_Credit_Card.csv` contains all 30,000 records and 25 columns from the UCI source spreadsheet. It is not a sample or synthetic dataset.

- Citation: Yeh, I. (2009). Default of Credit Card Clients [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C55S3H.
- Source: https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
- Original download: https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
- Conversion: read the original XLS with the second row as column headers; rename `default payment next month` to `default.payment.next.month` for compatibility with the existing Kaggle-based notebook; export UTF-8 CSV without an extra index. No client rows or numeric values were changed. Numeric round-trip equality was checked.
- Source XLS SHA-256: `30c6be3abd8dcfd3e6096c828bad8c2f011238620f5369220bd60cfc82700933`.
- CSV SHA-256: `f7b7d22d1f8dd27dadb25d4b78d8a4ae7c441ab6cc12d1ea58c0efc54d4d1788`.

This CSV was converted from UCI's XLS; it is not claimed to be a byte-identical copy of the Kaggle CSV. The data covers historical Taiwanese clients and April–September 2005 features. See the notebook for coding and interpretation notes.
