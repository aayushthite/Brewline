#!/usr/bin/env bash
# Remove everything Brewline created in the cluster.
set -euo pipefail
kubectl delete namespace brewline --ignore-not-found
kubectl delete clusterrole brewline-prometheus --ignore-not-found
kubectl delete clusterrolebinding brewline-prometheus --ignore-not-found
