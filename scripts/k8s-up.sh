#!/usr/bin/env bash
# Build images, load them into the kind cluster and install everything with Helm.
# Run from the repo root after:  kind create cluster --name athena --config k8s/kind-config.local.yaml
set -euo pipefail

# Optional: without a key, ai-service uses its rule-based fallback.
: "${ANTHROPIC_API_KEY:=}"
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "ANTHROPIC_API_KEY not set: explanations will use the rule-based fallback."
fi
DB_PASSWORD="${DB_PASSWORD:-athena-dev-password}"

for svc in api model_server ai_service monitor web; do
  name="athena-${svc//_/-}"
  docker build -f "services/$svc/Dockerfile" -t "$name:local" .
  kind load docker-image "$name:local" --name athena
done

# Prometheus + Grafana (release name must match serviceMonitor.releaseLabel)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace --wait

# metrics-server is needed for the HorizontalPodAutoscaler on kind
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' || true

kubectl create secret generic athena-secrets \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install athena helm/athena --wait

echo
echo "Athena is up. Open it with:"
echo "  kubectl port-forward svc/web 8080:8080        -> http://localhost:8080"
echo "  kubectl port-forward svc/api 8000:8000        (for scripts/stream_transactions.py)"
echo "  kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80  -> http://localhost:3000"
