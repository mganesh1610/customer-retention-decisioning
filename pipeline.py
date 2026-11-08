"""Reproducible telecom-risk benchmark and retention-budget reference implementation."""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import urllib.request
import zipfile

import lkml
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import sqlglot

ROOT = Path(__file__).resolve().parent
SOURCE_URL = "https://archive.ics.uci.edu/static/public/563/iranian%2Bchurn%2Bdataset.zip"
SOURCE_SHA256 = "696c3a1812267980751f30d19193a1b430ac4ad76172bb089e664c96813ead66"
FEATURES = ["call_failure", "complains", "subscription_length", "charge_amount",
            "seconds_of_use", "frequency_of_use", "frequency_of_sms",
            "distinct_called_numbers", "tariff_plan"]
EXCLUDED = ["status", "customer_value", "age", "age_group"]


def load_source(path: Path) -> pd.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
            path.write_bytes(response.read())
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Source hash mismatch: review changed upstream data before running")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        frame = pd.read_csv(archive.open("Customer Churn.csv"))
    frame.columns = ["_".join(c.lower().split()) for c in frame.columns]
    if frame.shape != (3150, 14) or frame.isna().any().any():
        raise ValueError("Unexpected source schema or missing values")
    if not set(frame.churn.unique()).issubset({0, 1}):
        raise ValueError("Non-binary churn target")
    frame.insert(0, "source_row", np.arange(1, len(frame) + 1))
    return frame


def group_split(frame: pd.DataFrame):
    # No source customer ID exists. Keep identical modeled feature vectors together.
    groups = pd.util.hash_pandas_object(frame[FEATURES], index=False).to_numpy()
    train_val, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42)
                           .split(frame, frame.churn, groups))
    train_rel, valid_rel = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=43)
                                .split(frame.iloc[train_val], frame.churn.iloc[train_val], groups[train_val]))
    return train_val[train_rel], train_val[valid_rel], test, groups


def top_k_metrics(y, probability, fraction=.2):
    n = max(1, math.ceil(len(y) * fraction))
    order = np.argsort(-np.asarray(probability), kind="stable")[:n]
    positives = int(np.asarray(y)[order].sum())
    prevalence = float(np.mean(y))
    return {"selected": n, "positive_labels": positives,
            "precision": positives / n,
            "recall": positives / int(np.sum(y)) if np.sum(y) else None,
            "lift_vs_random": (positives / n) / prevalence if prevalence else None}


def budget_plan(probability, config):
    """Rank expected retention value under configured budget and contact cost parameters."""
    cost = float(config["contact_cost"])
    if cost <= 0 or float(config["budget"]) < 0:
        raise ValueError("Positive contact cost and nonnegative budget required")
    rescue = float(config["rescue_probability_if_would_churn"])
    if not 0 <= rescue <= 1:
        raise ValueError("Rescue probability outside [0,1]")
    expected = np.asarray(probability) * rescue * float(config["margin_per_saved_customer"]) - cost
    order = np.argsort(-expected, kind="stable")
    eligible = order[expected[order] > 0]
    chosen = eligible[:int(float(config["budget"]) // cost)]
    return {"selected": int(len(chosen)), "contact_spend": len(chosen) * cost,
            "expected_net_scenario_units": float(expected[chosen].sum()),
            "expected_saved_scenario": float(np.asarray(probability)[chosen].sum() * rescue)}


def validate_lookml():
    parsed = {}
    for path in sorted((ROOT / "looker").glob("*.lkml")):
        parsed[path.name] = lkml.load(path.read_text())
    view = parsed["risk_scores.view.lkml"]["views"][0]
    dimensions = {field["name"] for field in view["dimensions"]}
    if not {"source_row", "tariff_plan", "risk_probability", "observed_churn"} <= dimensions:
        raise ValueError("Missing required semantic dimensions")
    if not any(d.get("primary_key") == "yes" for d in view["dimensions"]):
        raise ValueError("No semantic primary key")
    return {"files_parsed": len(parsed), "dimensions": len(dimensions),
            "measures": len(view["measures"]), "hosted_looker_validation": False}


def main():
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    frame = load_source(ROOT / "data/source.zip")
    train, valid, test, groups = group_split(frame)
    split_groups = [set(groups[ix]) for ix in (train, valid, test)]
    no_overlap = all(not split_groups[i] & split_groups[j] for i, j in ((0,1),(0,2),(1,2)))
    x, y = frame[FEATURES], frame.churn.to_numpy()
    candidates = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, random_state=42)),
        "random_forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=5, max_features=.8, random_state=42, n_jobs=2),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=15, l2_regularization=2.0, random_state=42),
    }
    comparison = []
    for name, model in candidates.items():
        model.fit(x.iloc[train], y[train])
        p = model.predict_proba(x.iloc[valid])[:, 1]
        comparison.append({"model": name, "validation_average_precision": float(average_precision_score(y[valid], p)),
                           "validation_brier": float(brier_score_loss(y[valid], p))})
    selected = max(comparison, key=lambda row: row["validation_average_precision"])["model"]
    model = candidates[selected]  # Frozen after validation; do not retrain on the test set.
    p = model.predict_proba(x.iloc[test])[:, 1]
    dummy = DummyClassifier(strategy="prior").fit(x.iloc[train], y[train])
    p0 = dummy.predict_proba(x.iloc[test])[:, 1]
    rng = np.random.default_rng(2026)
    unique_groups = np.unique(groups[test])
    group_rows = {g: np.flatnonzero(groups[test] == g) for g in unique_groups}
    auc_bootstrap = []
    for _ in range(500):
        ix = np.concatenate([group_rows[g] for g in rng.choice(unique_groups, len(unique_groups), replace=True)])
        if len(np.unique(y[test][ix])) == 2:
            auc_bootstrap.append(roc_auc_score(y[test][ix], p[ix]))
    predictions = frame.iloc[test][["source_row", "tariff_plan", "subscription_length"]].copy()
    predictions["risk_probability"] = p
    predictions["observed_churn"] = y[test]
    predictions["risk_band"] = pd.cut(p, bins=[-1,.2,.5,1], labels=["Lower", "Medium", "Higher"]).astype(str)
    predictions.to_csv(out / "holdout_scores.csv", index=False)
    db_path = out / "analytics.sqlite"
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as db:
        predictions.to_sql("risk_scores", db, index=False)
        db.execute("CREATE UNIQUE INDEX risk_row_key ON risk_scores(source_row)")
        cohorts = pd.read_sql_query((ROOT / "sql/cohort_metrics.sql").read_text(), db)
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    cohorts.to_csv(out / "cohort_metrics.csv", index=False)
    sqlglot.parse((ROOT / "sql/bigquery_setup.sql").read_text(), read="bigquery")
    config = json.loads((ROOT / "scenario.json").read_text())
    checks = {
        "source_rows": len(frame) == 3150,
        "source_churn_count": int(frame.churn.sum()) == 495,
        "split_row_conservation": len(train)+len(valid)+len(test) == len(frame),
        "modeled_feature_groups_disjoint": no_overlap,
        "excluded_features_absent": not set(FEATURES) & set(EXCLUDED),
        "finite_probabilities": bool(np.isfinite(p).all()),
        "probabilities_in_range": bool(((p >= 0) & (p <= 1)).all()),
        "cohort_count_reconciles": int(cohorts.scored_records.sum()) == len(test),
        "cohort_churn_reconciles": int(cohorts.observed_churns.sum()) == int(y[test].sum()),
        "sqlite_integrity": integrity == "ok",
        "positive_classes_in_each_split": all(len(set(y[ix])) == 2 for ix in (train,valid,test)),
        "semantic_and_sql_syntax": True,
    }
    report = {
        "source": {"url": SOURCE_URL, "sha256": SOURCE_SHA256, "rows": len(frame), "churn_labels": int(y.sum()),
                   "modeled_features": FEATURES, "excluded": EXCLUDED},
        "splits": {"train": len(train), "validation": len(valid), "test": len(test),
                   "feature_groups": len(set(groups)), "test_feature_groups": len(unique_groups),
                   "policy": "identical modeled vectors grouped across train/validation/test"},
        "model_selection": comparison, "selected_model": selected,
        "holdout": {"roc_auc": float(roc_auc_score(y[test], p)),
                    "roc_auc_group_bootstrap_95_ci": [float(n) for n in np.quantile(auc_bootstrap,[.025,.975])],
                    "average_precision": float(average_precision_score(y[test], p)),
                    "brier_score": float(brier_score_loss(y[test], p)),
                    "prior_brier_score": float(brier_score_loss(y[test], p0)),
                    "prevalence": float(y[test].mean()), "top_20_percent": top_k_metrics(y[test], p)},
        "retention_budget_scenario": {"assumptions": config, "result": budget_plan(p, config)},
        "semantic_validation": validate_lookml(),
        "checks": checks, "passed": sum(checks.values()), "failed": sum(not v for v in checks.values()),
        "execution": "Python, SQLite, LookML, and BigQuery SQL validation",
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "dashboard.html").write_text("<!doctype html><html><meta charset='utf-8'><title>Telecom retention review</title>"
        "<style>body{font:16px Arial;max-width:1000px;margin:40px auto;color:#20272c}h1{color:#173b55}"
        "td,th{padding:12px;text-align:right;border-bottom:1px solid #ddd}th{background:#edf3f8}</style>"
        "<h1>Telecom retention review</h1><p>Held-out evaluation with grouped feature-vector split. "
        "Charge amount is an ordinal predictor.</p>"
        f"<p>Model: {selected}. ROC-AUC: {report['holdout']['roc_auc']:.3f}. "
        f"Holdout records: {len(test):,}.</p>" + cohorts.to_html(index=False,float_format=lambda n:f"{n:.3f}") +
        "<p>Budget parameters and full validation are recorded in validation.json.</p></html>")
    print(json.dumps({"rows":len(frame),"splits":report["splits"],"selected_model":selected,
                      "holdout":report["holdout"],"checks_passed":report["passed"]}, indent=2))


if __name__ == "__main__":
    main()
