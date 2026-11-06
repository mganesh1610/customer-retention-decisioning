SELECT tariff_plan, risk_band, COUNT(*) AS scored_records,
       SUM(observed_churn) AS observed_churns,
       AVG(observed_churn) AS observed_churn_rate,
       AVG(risk_probability) AS average_predicted_risk
FROM risk_scores
GROUP BY tariff_plan, risk_band
ORDER BY tariff_plan, risk_band;
