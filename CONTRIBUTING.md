# How we work

## Branches and pull requests

1. Never push straight to `main`.
2. Create a branch for each task: `git checkout -b feature/owner-view` (or `fix/...`).
3. Commit small, clear changes: `git commit -m "Add review queue buttons"`.
4. Push and open a pull request. One teammate reviews it, CI must pass, then merge.
5. Pull often: `git pull origin main`.

## Who owns what

| Role | Folders |
| --- | --- |
| ML engineer | `ml/` |
| Backend | `services/api/` |
| Frontend | `services/web/` |
| DevOps | `helm/`, `k8s/`, `.github/`, Dockerfiles |
| AI + monitoring | `services/ai_service/`, `services/monitor/`, Grafana dashboards |

Add your name next to your role in the README.

## Rules

- Do not commit the dataset, model files or `.env` (they are in `.gitignore`).
- Do not change the API request/response shapes without telling the frontend and AI owners.
- If you change something another service depends on, say so in the pull request.
- Report real model numbers from `ml/artifacts/metrics.json`, never estimated ones.
