"""Load test for the Athena resilience demo. Standard library only.

Two modes:
  predict  Many concurrent /predict calls to model-server, to make the HPA scale up.
  orders   A steady stream of orders through the api (POST /api/transactions),
           to show that no orders fail while a model-server pod is deleted.

Run it inside the cluster so requests go through the Kubernetes Service and are
spread across all model-server pods (kubectl port-forward would hit only one pod):

  kubectl run loadgen --rm -i --restart=Never --image=athena-api:local -- \
    python -u - --mode predict --url http://model-server:8001 < scripts/load_test.py

  kubectl run orders --rm -i --restart=Never --image=athena-api:local -- \
    python -u - --mode orders --url http://api:8000 --rate 10 --duration 90 < scripts/load_test.py

Prints a summary line every 5 seconds and exits with code 1 if any request failed.
"""
import argparse
import json
import random
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Small built-in sample order, so no dataset or trained model is needed.
SAMPLE = {"TransactionAmt": 50.0, "ProductCD": "W", "card4": "visa", "card6": "debit",
          "P_emaildomain": "gmail.com", "DeviceType": "desktop"}


class Stats:
    """Thread-safe counters for one reporting window and for the whole run."""

    def __init__(self):
        self.lock = threading.Lock()
        self.total_ok = self.total_failed = 0
        self.window_ok = self.window_failed = 0
        self.window_latency = []
        self.errors = {}

    def record(self, ok: bool, latency: float, error: str | None = None):
        with self.lock:
            if ok:
                self.total_ok += 1
                self.window_ok += 1
                self.window_latency.append(latency)
            else:
                self.total_failed += 1
                self.window_failed += 1
                self.errors[error] = self.errors.get(error, 0) + 1

    def take_window(self):
        with self.lock:
            ok, failed, lat = self.window_ok, self.window_failed, sorted(self.window_latency)
            self.window_ok = self.window_failed = 0
            self.window_latency = []
        p95 = lat[int(len(lat) * 0.95) - 1] * 1000 if lat else 0.0
        return ok, failed, p95


def send(url: str, body: dict, timeout: float, stats: Stats):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        stats.record(True, time.perf_counter() - start)
    except urllib.error.HTTPError as exc:
        stats.record(False, 0, f"HTTP {exc.code}")
    except Exception as exc:  # connection refused, timeout, reset, ...
        stats.record(False, 0, type(exc).__name__)


def order_body(i: int) -> dict:
    tx = dict(SAMPLE, TransactionID=f"LOAD-{i}", TransactionAmt=round(random.uniform(5, 900), 2))
    return {"order_id": f"LOAD-{i}", "store_id": "load-test", "transaction": tx}


def reporter(stats: Stats, stop: threading.Event, interval: float):
    start = time.time()
    while not stop.wait(interval):
        ok, failed, p95 = stats.take_window()
        print(f"[{time.time() - start:5.0f}s] ok={ok:5d} failed={failed:3d} "
              f"rate={ok / interval:6.1f}/s p95={p95:6.0f}ms", flush=True)


def run_predict(args, stats: Stats, deadline: float):
    url = args.url.rstrip("/") + "/predict"

    def worker():
        while time.time() < deadline:
            body = {"transaction": dict(SAMPLE, TransactionAmt=round(random.uniform(5, 900), 2))}
            send(url, body, args.timeout, stats)

    with ThreadPoolExecutor(args.concurrency) as pool:
        for _ in range(args.concurrency):
            pool.submit(worker)


def run_orders(args, stats: Stats, deadline: float):
    url = args.url.rstrip("/") + "/api/transactions"
    with ThreadPoolExecutor(max(4, int(args.rate * 2))) as pool:
        i, next_at = 0, time.time()
        while time.time() < deadline:
            pool.submit(send, url, order_body(i), args.timeout, stats)
            i += 1
            next_at += 1 / args.rate
            time.sleep(max(0.0, next_at - time.time()))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["predict", "orders"], required=True)
    p.add_argument("--url", required=True, help="model-server URL (predict) or api URL (orders)")
    p.add_argument("--duration", type=float, default=180, help="seconds to run (default 180)")
    p.add_argument("--concurrency", type=int, default=32, help="predict mode: parallel requests (default 32)")
    p.add_argument("--rate", type=float, default=10, help="orders mode: orders per second (default 10)")
    p.add_argument("--timeout", type=float, default=15, help="per-request timeout in seconds (default 15)")
    args = p.parse_args()

    stats, stop = Stats(), threading.Event()
    print(f"mode={args.mode} url={args.url} duration={args.duration:.0f}s "
          + (f"concurrency={args.concurrency}" if args.mode == "predict" else f"rate={args.rate}/s"), flush=True)
    threading.Thread(target=reporter, args=(stats, stop, 5), daemon=True).start()
    deadline = time.time() + args.duration
    try:
        (run_predict if args.mode == "predict" else run_orders)(args, stats, deadline)
    except KeyboardInterrupt:
        print("interrupted", flush=True)
    stop.set()

    print(f"TOTAL ok={stats.total_ok} failed={stats.total_failed}", flush=True)
    for err, n in sorted(stats.errors.items(), key=lambda e: -e[1]):
        print(f"  {n:5d} x {err}", flush=True)
    raise SystemExit(1 if stats.total_failed else 0)


if __name__ == "__main__":
    main()
