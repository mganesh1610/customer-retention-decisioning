# Customer Retention Decisioning

A reproducible telecom churn benchmark with duplicate-aware evaluation, a retention budget scenario, SQL cohort reporting, and a LookML semantic layer.

## Run

Use Python 3.12 in a virtual environment.

```sh
python -m pip install -r requirements.txt
python pipeline.py
python -m unittest -v
```

The pipeline downloads the pinned source on first run. Raw data, individual holdout scores, and SQLite stay local. Aggregate results, validation JSON, unit-test output, and the HTML review are versioned under `results/`.

## Architecture

UCI archive → hash/schema validation → nine-feature model matrix → grouped train/validation/test split → three candidate classifiers → validation-only model choice → frozen test evaluation → SQLite cohort metrics, LookML views, and budget sensitivity.

The source has no customer identifier. Identical modeled feature vectors are kept in the same split to prevent duplicate contamination across partitions. Row identity is a file-position surrogate. Features summarize the first nine months; the source labels churn at month twelve.

## Executed results

The November 6, 2026 run used 3,150 source rows, including 495 positive churn labels. It split 1,886 training, 632 validation, and 632 test rows into non-overlapping modeled feature groups. Histogram gradient boosting won on validation average precision, without consulting test performance for selection.

On the 632-row test set, ROC-AUC was **0.977591** and average precision was **0.905162**. A 500-replicate group bootstrap gave a ROC-AUC interval of **0.959105–0.989349**. Brier score was **0.040979**, compared with **0.136414** for the training-prior baseline. The highest-risk 20% contained 95 of 103 positive holdout labels, a **92.23% recall** and **4.59× lift** over the observed random-targeting prevalence.

All **12 pipeline checks** and **7 boundary tests** passed. Two LookML files were parsed, and BigQuery SQL syntax was parsed with the BigQuery dialect.

## Analytical choices

- Compare standardized logistic regression, random forest, and histogram gradient boosting by validation average precision. Scaling is fitted only to training data.
- Exclude `Status`, `Customer Value`, `Age`, and `Age Group`. Status is too close to an operational outcome for this use case, customer-value derivation is not supplied, and demographic variables are unnecessary for the reference prioritization policy.
- AUC measures ranking. Average precision complements it for the minority outcome; Brier score measures squared probability error.
- The budget scenario ranks `p(churn) × rescue probability × margin − contact cost`, admits positive-value contacts, and caps spend at the configured budget. Scenario units never use the source's ordinal Charge Amount as currency.

## Semantic and cloud handoff

See [schema and semantic contracts](docs/schema.md). To connect Looker, load `results/holdout_scores.csv` into the table described by `sql/bigquery_setup.sql`, replace `your_project`, and configure the `analytics_bigquery` connection. Import the two files under `looker/` and run Looker's native validator before publishing. Suggested tiles are scored records, observed churn rate, mean predicted risk, and a tariff-plan/risk-band comparison. Never mix training predictions into the holdout dashboard.

The checked-in SQL provides a BigQuery deployment handoff alongside local SQLite execution.

## Data

Primary: [UCI Iranian Churn](https://archive.ics.uci.edu/dataset/563/iranian+churn+dataset), DOI [10.24432/C5JW3Z](https://doi.org/10.24432/C5JW3Z), 2020, CC BY 4.0. Source archive SHA-256: `696c3a1812267980751f30d19193a1b430ac4ad76172bb089e664c96813ead66`.

Backup, located but not run: [IBM Telco Customer Churn](https://github.com/IBM/telco-customer-churn-on-icp4d/blob/master/data/Telco-Customer-Churn.csv). Its sample-company records require a separate adapter. Map `customerID`, `tenure`, `Contract`, `MonthlyCharges`, `TotalCharges`, and `Churn`; handle blank TotalCharges explicitly. Do not append it to the UCI population or treat it as an independent cohort from the same operator.

The code is MIT licensed; the dataset retains its separate source license. Review changes to eligibility, split policy, metrics, or budget assumptions before using the outputs for a business decision.
