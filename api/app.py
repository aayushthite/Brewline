import os
import time
import uuid

import redis
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

MENU = {
    "espresso": 3.00,
    "cappuccino": 4.00,
    "latte": 4.50,
    "cold_brew": 5.00,
    "matcha": 5.50,
}
QUEUE = "orders:queue"
RECENT = "orders:recent"

r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

# ---------------- Prometheus metrics ----------------
ORDERS = Counter("brewline_orders_created_total", "Orders accepted by the API", ["drink"])
REVENUE = Counter("brewline_revenue_dollars_total", "Sum of accepted order prices")
HTTP_LATENCY = Histogram(
    "brewline_http_request_duration_seconds",
    "API request latency",
    ["method", "route", "status"],
)
QUEUE_DEPTH = Gauge("brewline_queue_depth", "Orders waiting for a barista")


def _queue_depth() -> float:
    try:
        return r.llen(QUEUE)
    except redis.RedisError:
        return float("nan")


QUEUE_DEPTH.set_function(_queue_depth)

app = FastAPI(title="Brewline API")


@app.middleware("http")
async def measure(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", "") or "static"
        HTTP_LATENCY.labels(request.method, route, str(status)).observe(time.perf_counter() - start)


class OrderIn(BaseModel):
    drink: str
    customer: str = "guest"


class ChaosIn(BaseModel):
    slowdown: float = 1.0
    fail_rate: float = 0.03


@app.get("/api/menu")
def menu():
    return [{"drink": d, "price": p} for d, p in MENU.items()]


@app.post("/api/orders", status_code=201)
def create_order(order: OrderIn):
    if order.drink not in MENU:
        raise HTTPException(400, f"unknown drink '{order.drink}'")
    order_id = uuid.uuid4().hex[:6]
    try:
        pipe = r.pipeline()
        pipe.hset(
            f"order:{order_id}",
            mapping={
                "id": order_id,
                "drink": order.drink,
                "customer": order.customer[:20],
                "status": "queued",
                "created": time.time(),
            },
        )
        pipe.expire(f"order:{order_id}", 3600)
        pipe.lpush(QUEUE, order_id)
        pipe.lpush(RECENT, order_id)
        pipe.ltrim(RECENT, 0, 7)
        pipe.llen(QUEUE)
        position = pipe.execute()[-1]
    except redis.RedisError:
        raise HTTPException(503, "order queue unavailable")
    ORDERS.labels(order.drink).inc()
    REVENUE.inc(MENU[order.drink])
    return {"id": order_id, "status": "queued", "position": position}


@app.get("/api/orders/recent")
def recent_orders():
    try:
        ids = r.lrange(RECENT, 0, 7)
        pipe = r.pipeline()
        for i in ids:
            pipe.hgetall(f"order:{i}")
        return [o for o in pipe.execute() if o]
    except redis.RedisError:
        raise HTTPException(503, "order store unavailable")


@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    order = r.hgetall(f"order:{order_id}")
    if not order:
        raise HTTPException(404, "order not found")
    return order


@app.get("/api/chaos")
def get_chaos():
    return {
        "slowdown": float(r.get("config:slowdown") or 1.0),
        "fail_rate": float(r.get("config:fail_rate") or 0.03),
    }


@app.post("/api/chaos")
def set_chaos(c: ChaosIn):
    """Practice hook: make the espresso machine slow or flaky so alerts fire."""
    slowdown = min(max(c.slowdown, 1.0), 10.0)
    fail_rate = min(max(c.fail_rate, 0.0), 1.0)
    r.set("config:slowdown", slowdown)
    r.set("config:fail_rate", fail_rate)
    return {"slowdown": slowdown, "fail_rate": fail_rate}


@app.get("/api/config")
def config():
    return {
        "grafana_url": os.getenv("GRAFANA_URL", ""),
        "prometheus_url": os.getenv("PROMETHEUS_URL", ""),
    }


@app.get("/healthz")
def healthz():
    try:
        r.ping()
    except redis.RedisError:
        raise HTTPException(503, "redis unreachable")
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Must be last: serves the storefront at /
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")
