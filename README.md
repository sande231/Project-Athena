# Project Athena

Athena keeps fraud-detection models accurate and easy to understand after they go live. It scores every online order, notices when fraud patterns change (data drift), and uses Claude (Anthropic API) to explain decisions and alerts in plain English.

Built for the Fall 2026 final project, Morgan State University. Full design: [`docs/Project_Athena_Documentation.pdf`](docs/Project_Athena_Documentation.pdf).

## How it works

```
Store plugin / demo store ──► athena-api ──► model-server   (fraud score 0–1)
                                  │     └──► ai-service ──► Anthropic API (one-line reason)
                                  ▼
                              PostgreSQL ◄── monitor-worker (drift check → Claude alert)
athena-web (Owner View, Engineer dashboard) reads from athena-api
Prometheus scrapes /metrics on every service → Grafana dashboards
```

Score below 0.3 = **Approve**, 0.3 to 0.7 = **Review**, above 0.7 = **Block**.

## Repo layout

| Folder | What's inside |
| --- | --- |
| `ml/` | `train.py` (LightGBM + Optuna), `features.py` (shared feature engineering), `drift.py` (PSI) |
| `services/api/` | Flask REST API and database models |
| `services/model_server/` | Loads the model, returns scores + top features |
| `services/ai_service/` | All Claude calls, with a rule-based fallback |
| `services/monitor/` | Drift and flag-rate checks, creates alerts |
| `services/web/` | Owner View, Engineer dashboard, demo store (HTML/CSS/JS + Plotly) |
| `helm/athena/` | Helm chart: deployments, services, HPA, Postgres, ServiceMonitor |
| `k8s/` | kind cluster config |
| `scripts/` | `stream_transactions.py` (replay orders / simulate attack), `k8s-up.sh` |
| `tests/` | pytest tests (run in CI) |

## Quick start (local, Docker Compose)

Requirements: Python 3.11, Docker Desktop.

```bash
# 1. Get the data (see ml/data/README.md), then train
python -m venv .venv && source .venv/bin/activate
pip install -r ml/requirements.txt
python ml/train.py --data ml/data --sample 100000        # add --tune --trials 20 for Optuna

# 2. (Optional) Add your Claude key
cp .env.example .env        # paste ANTHROPIC_API_KEY into .env
# Without it, explanations use simple rule-based text.

# 3. Run everything
docker compose up --build
# open http://localhost:8080
# Port 8080 in use? Run: WEB_PORT=8081 docker compose up --build
#   (or set WEB_PORT=8081 in .env), then open http://localhost:8081
docker compose ps           # every service except monitor should show (healthy)

# 4. Send traffic, then simulate an attack (in another terminal)
pip install pandas requests
python scripts/stream_transactions.py --rate 5 --limit 500
python scripts/stream_transactions.py --rate 5 --limit 300 --attack
```

Without an API key everything still runs; explanations fall back to simple rule-based text.

## Kubernetes (demo)

Requirements: Docker, [kind](https://kind.sigs.k8s.io/), kubectl, Helm. 16 GB RAM recommended.

```bash
# copy the template, then set hostPath to the absolute path of ml/artifacts on your machine
# (kind-config.local.yaml is gitignored, so your path is never committed; quote it if it has spaces)
cp k8s/kind-config.yaml k8s/kind-config.local.yaml
kind create cluster --name athena --config k8s/kind-config.local.yaml
export ANTHROPIC_API_KEY=sk-ant-...      # optional: without it, explanations use rule-based text
./scripts/k8s-up.sh
kubectl port-forward svc/web 8080:8080
```

`k8s-up.sh` builds and loads the images, installs Prometheus + Grafana (kube-prometheus-stack), metrics-server for autoscaling, the `athena-secrets` Secret, and the Athena chart.

Useful demo commands:

```bash
kubectl get pods -w                              # watch pods
kubectl delete pod -l app=model-server --wait=false   # Kubernetes restarts it
kubectl get hpa model-server -w                  # autoscaling under load
```

## Run the tests

```bash
pip install -r services/api/requirements.txt -r ml/requirements.txt pytest
pytest -q
```

## Team

| Role | Name |
| --- | --- |
| Project lead + ML | [name] |
| Backend | [name] |
| Frontend | [name] |
| DevOps | [name] |
| AI + monitoring | [name] |

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch and pull request workflow.

## Status (two-week scope)

- [x] Starter code for all services, tests, Docker Compose, Helm chart, CI
- [ ] Train on the real dataset and record metrics
- [ ] Grafana dashboard for Athena metrics
- [ ] Retrain button starts a real training job
- [ ] Demo rehearsal + backup video

## Dataset

[IEEE-CIS Fraud Detection](https://www.kaggle.com/competitions/ieee-fraud-detection) (Vesta, via Kaggle). Used for coursework under the competition rules; not redistributed here.
