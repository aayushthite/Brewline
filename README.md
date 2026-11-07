# Brewline

A tiny coffee-shop order pipeline built to practise **Docker, Kubernetes, Prometheus and Grafana** on something that behaves like a real system. Customers place orders, baristas brew them from a queue, and every step exports metrics. You can break the espresso machine on purpose and watch alerts and dashboards react.

It is deliberately small: three Python services, one Redis, no database to babysit, so your time goes into the platform tooling.

## Architecture

```
  simulated customers                                   +-------------+
  +-----------+  POST /api/orders   +-----------+       |  Prometheus |  scrapes /metrics
  |  loadgen  | ------------------> |    api    | ----> |  + alert    |  every 5s
  +-----------+                     | (FastAPI) |  ^    |    rules    |
                                    +-----+-----+  |    +------+------+
  browser -----> storefront UI -----------+        |           |
                                          | LPUSH  |           v
                                    +-----v-----+  |    +-------------+
                                    |   Redis   |  |    |   Grafana   |
                                    |   queue   |--+    |  dashboard  |
                                    +-----+-----+  ^    +-------------+
                                          | BRPOP  |
                                    +-----v-----+  |  redis-exporter turns Redis
                                    |  worker   |--+  internals into metrics
                                    | x2 (brew) |
                                    +-----------+
```

| Piece | What it is | Why it is in the project |
|---|---|---|
| `api` | FastAPI: menu, orders, serves the storefront, `/metrics` | counters, gauges, histograms; health probes |
| `worker` | Pulls orders from Redis and "brews" them (2 replicas) | scaling, graceful shutdown, histograms |
| `loadgen` | Customers arriving in a rush-hour wave | live data without clicking |
| `redis` + `redis-exporter` | Queue and order state, plus exporter | exporter and sidecar patterns |
| `prometheus` | Scrapes, stores, evaluates `monitoring/alerts.yml` | PromQL, service discovery, alerting rules |
| `grafana` | Auto-provisioned datasource and 16-panel dashboard | dashboards as code |

## 1. Run with Docker Compose

Prerequisites: Docker with the Compose plugin.

```bash
docker compose up --build -d
docker compose ps
```

| URL | What |
|---|---|
| http://localhost:8000 | Storefront (order drinks, break the machine) |
| http://localhost:3000 | Grafana, login `admin` / `admin`, dashboard "Brewline: shop floor" opens by default |
| http://localhost:9090 | Prometheus (try Status > Targets, and Alerts) |
| http://localhost:8000/metrics | Raw metrics from the API, exactly what Prometheus reads |

Give it about 30 seconds and the dashboard fills with data.

Handy commands:

```bash
docker compose logs -f worker                 # watch baristas work
docker compose up -d --scale worker=4         # hire more baristas
docker compose stop redis                     # kill the queue, watch alerts and errors
docker compose exec redis redis-cli llen orders:queue
docker compose down -v                        # stop and delete all data
```

## 2. Experiments (this is the actual learning)

**Docker**
1. Read the three Dockerfiles. Why is `requirements.txt` copied before the code? (layer caching)
2. `docker compose up -d --scale worker=4`, then check Prometheus Status > Targets. Nobody edited a config file, so how did it find the new workers? (DNS service discovery in `monitoring/prometheus.yml`)
3. `docker compose stop worker`. Watch queue depth climb, then the `WorkerDown` alert go pending, then firing. Start it again and watch the queue drain.
4. `docker stats` while the load runs. Compare with the "Process CPU/memory" panels.

**Prometheus**
1. Open http://localhost:9090/graph and try the queries in the cheat sheet below.
2. Click "Break the machine" in the storefront. Within about a minute `SlowBrewing` and `HighFailureRate` should go Pending, then Firing, in the Alerts tab.
3. Edit a threshold in `monitoring/alerts.yml`, then reload without restarting: `curl -X POST localhost:9090/-/reload`.

**Grafana**
1. Edit a panel, press "Query inspector", and see the PromQL behind it.
2. Build your own panel: "Average price per order" = `sum(rate(brewline_revenue_dollars_total[5m])) / sum(rate(brewline_orders_created_total[5m]))`.
3. Add a threshold line at 10 seconds on the brew-time panel.
4. Dashboards are files: change one in the UI, use Share > Export > JSON, and replace `monitoring/grafana/dashboards/brewline.json`.

### PromQL cheat sheet

| Metric type | Example in this project | Typical query |
|---|---|---|
| Counter (only goes up) | `brewline_orders_created_total` | `rate(x[1m])` for per-second, `increase(x[1h])` for totals |
| Gauge (goes up and down) | `brewline_queue_depth` | use directly, or `max`/`avg` across replicas |
| Histogram (buckets) | `brewline_brew_duration_seconds_bucket` | `histogram_quantile(0.95, sum by (le) (rate(x_bucket[1m])))` |

Also try: `sum by (drink) (rate(brewline_orders_created_total[5m]))`, `up`, `process_resident_memory_bytes`, `redis_connected_clients`.

## 3. Run on Kubernetes (minikube)

```bash
minikube start --memory=4096
eval $(minikube docker-env)       # build images inside minikube's Docker
docker compose build
./scripts/k8s-up.sh
minikube service api -n brewline          # storefront
minikube service grafana -n brewline      # admin / admin
minikube service prometheus -n brewline
```

kind instead of minikube: build with `docker compose build`, run `kind load docker-image brewline/api:latest brewline/worker:latest brewline/loadgen:latest`, then `./scripts/k8s-up.sh` and `kubectl -n brewline port-forward svc/grafana 3000:3000`.

How monitoring works here: pods carry annotations (`prometheus.io/scrape: "true"`, `prometheus.io/port`). Prometheus asks the Kubernetes API for pods (that is why `k8s/30-prometheus.yaml` has a ClusterRole) and scrapes the annotated ones. The Redis exporter runs as a **sidecar** in the Redis pod.

Kubernetes experiments:
```bash
kubectl -n brewline get pods -w
kubectl -n brewline delete pod -l app=worker       # self-healing, see the queue wobble
kubectl -n brewline scale deploy/worker --replicas=5
kubectl -n brewline logs -l app=worker --tail=20 -f
kubectl -n brewline set image deploy/api api=brewline/api:v2   # a broken rollout: watch it stall
kubectl -n brewline rollout undo deploy/api
kubectl -n brewline top pods                       # needs: minikube addons enable metrics-server
kubectl apply -f k8s/optional/hpa-worker.yaml      # autoscaling exercise
```

If you change anything in `monitoring/`, rerun `./scripts/k8s-up.sh` and then `kubectl -n brewline rollout restart deploy/prometheus deploy/grafana`. Remove everything with `./scripts/k8s-down.sh`.

## 4. Tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r api/requirements-dev.txt
(cd api && python -m pytest -q)
(cd worker && python -m pytest -q)
```

## 5. Push to GitHub

```bash
git init && git add . && git commit -m "Brewline: Docker, Kubernetes, Prometheus, Grafana practice project"
git branch -M main
git remote add origin https://github.com/<your-username>/brewline.git
git push -u origin main
```

## Where to go next

- Add **Alertmanager** so alerts send to Slack or email, not only the Prometheus UI.
- Add a **Jenkinsfile**: run the tests, `docker compose build`, push images to a registry.
- Write a **Helm chart** for the apps, replacing the plain YAML.
- Provision an AWS box or EKS cluster with **Terraform** and run the same stack there.
- Add **Loki** for logs next to the metrics in Grafana.
- Add a **PostgreSQL** database for permanent order history, with `postgres_exporter`.

## Practice-only shortcuts (do not copy to production)

- Grafana password is `admin`, and `/api/chaos` has no authentication. That endpoint exists only so you can break things safely.
- Redis has no password and no persistence guarantees for the queue.
- Plain HTTP everywhere.
