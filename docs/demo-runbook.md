# Resilience demo runbook

Shows two things on the local kind cluster:

1. **Autoscaling.** Under load, model-server grows from 2 to 6 pods, then shrinks back to 2.
2. **Self-healing.** A model-server pod is deleted while orders are flowing, and no order fails.

It works with the placeholder heuristic model, so no trained model is needed.
Total time is about 8 minutes.

The timings below were measured on 2026-11-19 (10-CPU Mac, Docker with about 9.7 GB of memory).
Expect similar but not identical numbers on other machines.

## Before the presentation

The cluster must be up (see the README, "Kubernetes (demo)"):

```bash
kind create cluster --name athena --config k8s/kind-config.local.yaml
./scripts/k8s-up.sh
```

On a fresh cluster, wait about 3 minutes after `k8s-up.sh` finishes. Prometheus takes that
long to start scraping the Athena services.

Arrange three terminals side by side, all opened at the repo root:

| Terminal | Purpose |
| --- | --- |
| **T1** | Watch the autoscaler |
| **T2** | Watch the model-server pods |
| **T3** | Run the demo commands |

## Step 0: Preflight (T3)

```bash
kubectl get pods
kubectl get hpa model-server
```

**Audience sees:** every pod `Running` and `1/1`, with 0 restarts. The HPA shows `REPLICAS 2`,
with CPU well below the `70%` target.

If the HPA's CPU column shows `<unknown>`, metrics-server is still starting. Wait about 30 seconds.

## Step 1: Start the watches

T1:
```bash
kubectl get hpa model-server -w
```

T2:
```bash
kubectl get pods -l app=model-server -w
```

**Audience sees:** two model-server pods, and the HPA at 2 replicas.

## Step 2: Scale up under load (T3, about 3 minutes)

```bash
kubectl run loadgen --rm -i --restart=Never --image=athena-api:local -- \
  python -u - --mode predict --url http://model-server:8001 --duration 180 < scripts/load_test.py
```

The load generator runs inside the cluster, so the Kubernetes Service spreads its requests across
all model-server pods. Every 5 seconds it prints a line with the requests that succeeded, the
requests that failed, the request rate, and the p95 latency.

**Audience sees:**

| Time after start | What happens |
| --- | --- |
| 0 to 30 s | CPU in T1 climbs above the 70% target. Metrics take about 30 seconds to show up. |
| about 40 s | The HPA asks for 6 replicas, and 4 new pods appear in T2 (`ContainerCreating` → `Running`). |
| about 60 s | T1 shows 6 replicas. |
| until the end | In T3, the request rate rises from about 3,000/s (2 pods, p95 about 35 ms) to about 4,000/s (6 pods, p95 about 14 ms). `failed=0` throughout. |

**Point to make:** Kubernetes added capacity automatically when traffic grew. Throughput went
up and latency went down, and no one had to step in.

It ends with `TOTAL ok=... failed=0`. The measured run was `ok=692870 failed=0`.

## Step 3: Scale down (about 2 minutes, no command)

Stay on T1 and T2 after the load stops.

**Audience sees:**

| Time after the load stops | What happens |
| --- | --- |
| about 30 s | CPU drops to around 1%. |
| about 70 s | The HPA scales to 4 replicas, and pods show as `Terminating` in T2. |
| about 100 s | Back to 2 replicas. |

**Point to make:** capacity shrinks again when it isn't needed, so resources aren't wasted.

The chart sets a 60-second scale-down window (`scaleDownSeconds` in `helm/athena/values.yaml`)
to keep the demo short. Production would keep the Kubernetes default of 5 minutes.

## Step 4: Delete a pod while orders flow (T3, about 90 seconds)

Wait until T1 shows 2 replicas again. Then start a steady stream of 10 orders per second
through the api:

```bash
kubectl run orders --rm -i --restart=Never --image=athena-api:local -- \
  python -u - --mode orders --url http://api:8000 --rate 10 --duration 90 < scripts/load_test.py
```

About 20 seconds in, open a **fourth terminal** (or use T1 after stopping its watch with Ctrl+C).
Delete **one** model-server pod:

```bash
kubectl delete "$(kubectl get pods -l app=model-server -o name | head -1)" --wait=false
```

Do not use `kubectl delete pod -l app=model-server`. That deletes every model-server pod at once.

You can delete a second pod about 30 seconds later to make the point twice.

**Audience sees:**

- **T2:** the deleted pod shows `Terminating`. A replacement appears, goes `ContainerCreating` →
  `Running`, and becomes `1/1` (Ready).
- **T3:** each line keeps `ok` at about 50 per 5 seconds and `failed=0`. The run ends with
  about 900 ok and 0 failed (measured: `TOTAL ok=901 failed=0`, with two pods deleted).

**Point to make:** a server crashed in the middle of traffic, and customers didn't notice.
Kubernetes replaced the pod, and the remaining pod handled orders in the meantime.

Measured results:

| Chart setting | Pod deletions | Result |
| --- | --- | --- |
| With `preStopSleep: 5` (current chart) | 5 in 130 s | `ok=1300 failed=0` |
| Without it | 3 in 80 s | `ok=799 failed=1` (one HTTP 503) |

This explains why the chart has the `preStopSleep` setting. When a pod starts shutting down, it
keeps serving for 5 seconds while Kubernetes stops sending it new requests.

## If something goes wrong

| Symptom | Fix |
| --- | --- |
| `pods "loadgen" already exists` or `pods "orders" already exists` | A previous run was interrupted. Run `kubectl delete pod loadgen orders --ignore-not-found`. |
| HPA shows `<unknown>` for CPU | Run `kubectl -n kube-system get pods -l k8s-app=metrics-server` and wait until the pod is `Running`. |
| New pods stay `Pending` | Docker is out of memory or CPU. Run `kubectl describe pod <name>` and read the Events section. Give Docker more resources, or lower `--concurrency`. |
| The HPA stays at 2 under load | Wait 60 seconds, because the metrics lag. Check that T3 shows a high request rate. |
| Orders print `failed>0` | Check that `kubectl get pods` shows api and postgres `Running`, and that `kubectl logs deploy/api` has no database errors. |

## Reset between rehearsals

There's nothing to reset. The load generator pods remove themselves (`--rm`), and the HPA scales
back to 2 by itself. Test orders from Step 4 go into the cluster's database with
`store_id=load-test`. A full reset is `kind delete cluster --name athena`, then the setup
commands at the top.
