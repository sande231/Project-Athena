"""Replay held-out IEEE-CIS rows into Athena as if they were live orders.

Normal traffic:
    python scripts/stream_transactions.py --rate 5
Simulated fraud attack (for the demo):
    python scripts/stream_transactions.py --rate 5 --attack

--attack changes each order to look like a new fraud pattern: higher amounts,
an email domain the model never saw, and mobile devices. The monitor should
detect drift within a few checks and Claude should explain it.
"""
import argparse
import math
import time

import pandas as pd
import requests


def clean(row: dict) -> dict:
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items() if k != "isFraud"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default="ml/artifacts/live_stream.csv")
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--rate", type=float, default=5, help="orders per second")
    p.add_argument("--limit", type=int, default=2000)
    p.add_argument("--attack", action="store_true")
    args = p.parse_args()

    df = pd.read_csv(args.file, nrows=args.limit)
    print(f"streaming {len(df)} orders at {args.rate}/s {'(ATTACK MODE)' if args.attack else ''}")
    for i, row in enumerate(df.to_dict("records")):
        tx = clean(row)
        if args.attack:
            tx["TransactionAmt"] = round((tx.get("TransactionAmt") or 50) * 4, 2)
            tx["P_emaildomain"] = "fastmail-x.biz"
            tx["DeviceType"] = "mobile"
        try:
            r = requests.post(f"{args.api}/api/transactions", json={"order_id": f"S-{tx['TransactionID']}",
                                                                    "transaction": tx}, timeout=15).json()
            print(f"{i:5d} {r.get('decision', r.get('error')):8s} score={r.get('score')}")
        except Exception as exc:
            print("error:", exc)
        time.sleep(1 / args.rate)


if __name__ == "__main__":
    main()
