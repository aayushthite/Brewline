#!/usr/bin/env bash
# Deploy Brewline to the current kubectl context (minikube / kind / EKS).
# The monitoring config lives in monitoring/ and is turned into ConfigMaps here,
# so Compose and Kubernetes share the same alert rules and dashboard.
set -euo pipefail
cd "$(dirname "$0")/.."

kubectl apply -f k8s/00-namespace.yaml

mkcm() { # mkcm <name> <kubectl create configmap args...>
  local name=$1; shift
  kubectl -n brewline create configmap "$name" "$@" --dry-run=client -o yaml | kubectl apply -f -
}

mkcm prometheus-config \
  --from-file=prometheus.yml=monitoring/prometheus-k8s.yml \
  --from-file=alerts.yml=monitoring/alerts.yml
mkcm grafana-datasource \
  --from-file=datasource.yml=monitoring/grafana/provisioning/datasources/datasource.yml
mkcm grafana-dashboard-provider \
  --from-file=provider.yml=monitoring/grafana/provisioning/dashboards/provider.yml
mkcm grafana-dashboards \
  --from-file=brewline.json=monitoring/grafana/dashboards/brewline.json

kubectl apply -f k8s/   # top-level files only; k8s/optional is skipped on purpose

for d in redis api worker loadgen prometheus grafana; do
  kubectl -n brewline rollout status deploy/$d --timeout=180s
done

echo
echo "Brewline is up. Open the three UIs:"
echo "  minikube service api        -n brewline   (storefront)"
echo "  minikube service prometheus -n brewline"
echo "  minikube service grafana    -n brewline   (admin / admin)"
echo "Or with any cluster:  kubectl -n brewline port-forward svc/grafana 3000:3000"
