# Schema and validation contracts

## Source

One row represents one anonymized customer snapshot. The CSV has 3,150 rows and 14 fields. Whitespace is normalized and columns become snake case.

| Source column | Normalized column | Use |
| --- | --- | --- |
| Call Failure | call_failure | Numeric predictor |
| Complains | complains | Binary predictor |
| Subscription Length | subscription_length | Numeric predictor in months |
| Charge Amount | charge_amount | Ordinal predictor, not money |
| Seconds of Use | seconds_of_use | Numeric predictor |
| Frequency of use | frequency_of_use | Numeric predictor |
| Frequency of SMS | frequency_of_sms | Numeric predictor |
| Distinct Called Numbers | distinct_called_numbers | Numeric predictor |
| Tariff Plan | tariff_plan | Binary coded predictor |
| Status | status | Excluded |
| Customer Value | customer_value | Excluded |
| Age | age | Excluded |
| Age Group | age_group | Excluded |
| Churn | churn | Binary outcome |

`source_row` is a generated one-based file position. It is not a recovered customer identity. No missing values are expected in the pinned file. Exact feature vectors define split groups; no rows are discarded.

## Reporting table

`risk_scores` contains test rows only: `source_row INTEGER UNIQUE`, `tariff_plan INTEGER`, `subscription_length INTEGER`, `risk_probability REAL [0,1]`, `observed_churn INTEGER {0,1}`, `risk_band TEXT {Lower, Medium, Higher}`. Bands are ≤0.2, >0.2–0.5, and >0.5. They are descriptive dashboard bands, not tuned operational thresholds.

`cohort_metrics` has one row per tariff plan and risk band. `scored_records` is COUNT(*); `observed_churns` is SUM(observed_churn); `observed_churn_rate` is churns / records; `average_predicted_risk` is AVG(risk_probability). The LookML measures retain the same denominators. Group totals reconcile to the test row and label counts. No joins multiply customer rows.

`scenario.json` owns every financial assumption. `retention_budget_scenario` in validation JSON records the assumptions and result together; `observed_retention_effect` remains null.

## Rebuild checks

Hash and schema contract, source and churn counts, row conservation, group disjointness, excluded-feature check, finite bounded scores, class coverage, SQL count/label reconciliation, SQLite integrity, LookML parsing, and BigQuery SQL parsing. Re-running replaces the local database. The seven unit tests exercise grouping, zero and insufficient budgets, non-positive costs, loss-making contacts, top-quintile arithmetic, and semantic completeness.
