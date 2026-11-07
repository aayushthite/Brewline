"""Barista worker: pulls orders off the Redis queue, 'brews' them, records metrics."""
import os
import random
import signal
import time

import redis
from prometheus_client import Counter, Gauge, Histogram, start_http_server

QUEUE = "orders:queue"
# (min, max) seconds to brew each drink at normal speed
BREW_SECONDS = {
    "espresso": (2, 4),
    "cappuccino": (4, 6),
    "latte": (4, 7),
    "cold_brew": (1, 2),
    "matcha": (5, 8),
}

BREW = Histogram(
    "brewline_brew_duration_seconds",
    "Time spent brewing one drink",
    ["drink"],
    buckets=(1, 2, 3, 4, 5, 6, 8, 10, 15, 30),
)
WAIT = Histogram(
    "brewline_order_wait_seconds",
    "End-to-end time from order placed to drink finished",
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300),
)
PROCESSED = Counter("brewline_orders_processed_total", "Finished orders", ["drink", "outcome"])
BUSY = Gauge("brewline_baristas_busy", "1 while this worker is brewing, else 0")

stopping = False


def _stop(*_):
    global stopping
    stopping = True  # finish the current drink, then exit (graceful shutdown)


def process_one(r, order_id, rng=random, sleep=time.sleep):
    """Brew a single order. Returns the outcome ('ready' or 'failed')."""
    order = r.hgetall(f"order:{order_id}")
    if not order:
        return None
    drink = order.get("drink", "espresso")
    low, high = BREW_SECONDS.get(drink, (2, 4))
    slowdown = float(r.get("config:slowdown") or 1.0)
    fail_rate = float(r.get("config:fail_rate") or 0.03)

    r.hset(f"order:{order_id}", "status", "brewing")
    BUSY.set(1)
    duration = rng.uniform(low, high) * slowdown
    sleep(duration)
    BUSY.set(0)

    outcome = "failed" if rng.random() < fail_rate else "ready"
    r.hset(f"order:{order_id}", "status", outcome)
    BREW.labels(drink).observe(duration)
    WAIT.observe(max(time.time() - float(order.get("created", time.time())), 0))
    PROCESSED.labels(drink, outcome).inc()
    return outcome


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    start_http_server(int(os.getenv("METRICS_PORT", "8001")))
    r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    print("worker: ready, waiting for orders", flush=True)
    while not stopping:
        try:
            item = r.brpop(QUEUE, timeout=2)
            if item:
                outcome = process_one(r, item[1])
                print(f"worker: order {item[1]} -> {outcome}", flush=True)
        except redis.RedisError as err:
            print(f"worker: redis problem ({err}); retrying", flush=True)
            time.sleep(2)
    print("worker: shut down cleanly", flush=True)


if __name__ == "__main__":
    main()
