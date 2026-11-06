view: risk_scores {
  sql_table_name: `your_project.retention.risk_scores` ;;
  dimension: source_row { primary_key: yes type: number sql: ${TABLE}.source_row ;; }
  dimension: tariff_plan { type: number sql: ${TABLE}.tariff_plan ;; }
  dimension: subscription_length { type: number sql: ${TABLE}.subscription_length ;; }
  dimension: risk_band { type: string sql: ${TABLE}.risk_band ;; }
  dimension: risk_probability { type: number sql: ${TABLE}.risk_probability ;; }
  dimension: observed_churn { type: number sql: ${TABLE}.observed_churn ;; }
  measure: scored_records { type: count }
  measure: observed_churns { type: sum sql: ${observed_churn} ;; }
  measure: observed_churn_rate {
    type: number value_format_name: percent_1
    sql: SAFE_DIVIDE(${observed_churns}, ${scored_records}) ;;
  }
  measure: mean_predicted_risk { type: average sql: ${risk_probability} ;; value_format_name: percent_1 }
}
