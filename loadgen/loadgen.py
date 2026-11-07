"""Simulated customers. Rate follows a sine wave so the dashboards show a 'rush hour'."""
import json
import math
import os
import random
import time
import urllib.error
import urllib.request

API_URL = os.getenv("API_URL", "http://api:8000")
BASE_RATE = float(os.getenv("ORDERS_PER_MIN", "20"))   # average orders per minute
WAVE_SECONDS = float(os.getenv("WAVE_SECONDS", "300"))  # length of one rush-hour cycle
NAMES = ["asha", "ben", "chen", "dara", "eli", "fatima", "gus", "hana", "ivan", "jo"]
DRINKS = ["espresso", "cappuccino", "latte", "cold_brew", "matcha"]
WEIGHTS = [30, 20, 25, 15, 10]


def place_order():
    body = json.dumps({"drink": random.choices(DRINKS, WEIGHTS)[0], "customer": random.choice(NAMES)})
    req = urllib.request.Request(
        f"{API_URL}/api/orders", data=body.encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        return res.status


def main():
    print(f"loadgen: {BASE_RATE}/min average against {API_URL}", flush=True)
    start = time.time()
    while True:
        phase = (time.time() - start) / WAVE_SECONDS * 2 * math.pi
        rate = max(BASE_RATE * (1 + 0.8 * math.sin(phase)), 1.0)  # orders per minute right now
        try:
            place_order()
        except (urllib.error.URLError, OSError) as err:
            print(f"loadgen: api not reachable yet ({err})", flush=True)
            time.sleep(3)
            continue
        time.sleep(random.expovariate(rate / 60.0))  # random gaps, like real customers


if __name__ == "__main__":
    main()
