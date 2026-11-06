-- Deployment handoff; replace your_project and load results/holdout_scores.csv.
-- No cloud query or billed resource is created by the local pipeline.
CREATE TABLE IF NOT EXISTS `your_project.retention.risk_scores` (
  source_row INT64 NOT NULL,
  tariff_plan INT64,
  subscription_length INT64,
  risk_probability FLOAT64,
  observed_churn INT64,
  risk_band STRING
)
CLUSTER BY tariff_plan, risk_band;

SELECT tariff_plan, risk_band, COUNT(*) AS scored_records,
       SUM(observed_churn) AS observed_churns,
       SAFE_DIVIDE(SUM(observed_churn), COUNT(*)) AS observed_churn_rate,
       AVG(risk_probability) AS average_predicted_risk
FROM `your_project.retention.risk_scores`
GROUP BY tariff_plan, risk_band;
