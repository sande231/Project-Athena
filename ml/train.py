"""Train the Athena fraud model on the IEEE-CIS dataset.

Usage:
    python ml/train.py --data ml/data --sample 100000
    python ml/train.py --data ml/data --sample 100000 --tune --trials 20

Outputs (in --out, default ml/artifacts):
    model.joblib          model + category maps + feature list
    reference_stats.json  training distributions for drift checks
    metrics.json          validation metrics (report these, not made-up numbers)
    live_stream.csv       the latest ~20% of rows, replayed by scripts/stream_transactions.py
"""
import argparse
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, roc_auc_score

import drift
import features as F

THRESHOLD_REVIEW = 0.3
THRESHOLD_BLOCK = 0.7


def load(data_dir: Path, sample: int | None) -> pd.DataFrame:
    tx = pd.read_csv(data_dir / "train_transaction.csv")
    identity_path = data_dir / "train_identity.csv"
    if identity_path.exists():
        tx = tx.merge(pd.read_csv(identity_path), on="TransactionID", how="left")
    tx = tx.sort_values("TransactionDT").reset_index(drop=True)
    if sample and sample < len(tx):
        # keep time order: take evenly spaced rows
        tx = tx.iloc[np.linspace(0, len(tx) - 1, sample).astype(int)].reset_index(drop=True)
    return tx


def evaluate(y, scores) -> dict:
    flagged = scores >= THRESHOLD_BLOCK
    return {
        "roc_auc": round(float(roc_auc_score(y, scores)), 4),
        "precision_at_block": round(float(precision_score(y, flagged, zero_division=0)), 4),
        "recall_at_block": round(float(recall_score(y, flagged, zero_division=0)), 4),
        "false_positive_rate": round(float(((flagged == 1) & (y == 0)).sum() / max((y == 0).sum(), 1)), 4),
        "fraud_rate": round(float(y.mean()), 4),
        "rows": int(len(y)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="ml/data")
    parser.add_argument("--out", default="ml/artifacts")
    parser.add_argument("--sample", type=int, default=100_000)
    parser.add_argument("--tune", action="store_true", help="tune with Optuna")
    parser.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df = load(Path(args.data), args.sample)
    n = len(df)
    train, valid, live = df.iloc[: int(n * 0.7)], df.iloc[int(n * 0.7): int(n * 0.8)], df.iloc[int(n * 0.8):]
    print(f"rows: train={len(train)} valid={len(valid)} live={len(live)}")

    cat_maps = F.fit_category_maps(train)
    X_tr, y_tr = F.prepare(train, cat_maps), train["isFraud"].values
    X_va, y_va = F.prepare(valid, cat_maps), valid["isFraud"].values
    pos_weight = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)

    params = dict(n_estimators=400, learning_rate=0.05, num_leaves=64, subsample=0.8,
                  subsample_freq=1, colsample_bytree=0.8, scale_pos_weight=pos_weight, verbose=-1)

    if args.tune:
        import optuna

        def objective(trial):
            p = dict(params,
                     num_leaves=trial.suggest_int("num_leaves", 16, 256, log=True),
                     learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                     min_child_samples=trial.suggest_int("min_child_samples", 10, 200),
                     colsample_bytree=trial.suggest_float("colsample_bytree", 0.4, 1.0))
            m = lgb.LGBMClassifier(**p).fit(X_tr, y_tr)
            return roc_auc_score(y_va, m.predict_proba(X_va)[:, 1])

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=args.trials)
        params.update(study.best_params)
        json.dump({"best_params": study.best_params, "best_auc": study.best_value,
                   "trials": len(study.trials)}, open(out / "tuning.json", "w"), indent=2)
        print("best params:", study.best_params)

    model = lgb.LGBMClassifier(**params).fit(X_tr, y_tr)
    lgb_scores = model.predict_proba(X_va)[:, 1]

    baseline = LogisticRegression(max_iter=1000, class_weight="balanced")
    baseline.fit(X_tr.fillna(0), y_tr)
    base_scores = baseline.predict_proba(X_va.fillna(0))[:, 1]

    metrics = {"lightgbm": evaluate(y_va, lgb_scores), "logistic_baseline": evaluate(y_va, base_scores),
               "thresholds": {"review": THRESHOLD_REVIEW, "block": THRESHOLD_BLOCK}, "params": params}
    print(json.dumps(metrics, indent=2, default=float))

    reference = {c: drift.numeric_reference(train[c]) for c in F.DRIFT_NUMERIC if c in train}
    reference.update({c: drift.categorical_reference(train[c]) for c in F.DRIFT_CATEGORICAL if c in train})

    joblib.dump({"model": model, "category_maps": cat_maps, "features": F.FEATURE_COLUMNS,
                 "thresholds": metrics["thresholds"]}, out / "model.joblib")
    json.dump(reference, open(out / "reference_stats.json", "w"), indent=2)
    json.dump(metrics, open(out / "metrics.json", "w"), indent=2, default=float)
    live.to_csv(out / "live_stream.csv", index=False)
    print(f"saved model and stats to {out}/")


if __name__ == "__main__":
    main()
