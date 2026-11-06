connection: "analytics_bigquery"
include: "/*.view.lkml"
explore: risk_scores {
  label: "Retention Risk Review"
  description: "Historical held-out benchmark scores; not live customers or causal treatment effects."
}
