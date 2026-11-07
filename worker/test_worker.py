import fakeredis

import worker


class FixedRng:
    """Deterministic stand-in for the random module."""

    def __init__(self, roll):
        self.roll = roll

    def uniform(self, low, high):
        return low

    def random(self):
        return self.roll


def make_order(r, drink="espresso"):
    r.hset("order:abc", mapping={"id": "abc", "drink": drink, "status": "queued", "created": "0"})


def test_successful_order_becomes_ready():
    r = fakeredis.FakeRedis(decode_responses=True)
    make_order(r)
    assert worker.process_one(r, "abc", rng=FixedRng(0.99), sleep=lambda s: None) == "ready"
    assert r.hget("order:abc", "status") == "ready"


def test_flaky_machine_fails_order():
    r = fakeredis.FakeRedis(decode_responses=True)
    make_order(r)
    r.set("config:fail_rate", 1.0)
    assert worker.process_one(r, "abc", rng=FixedRng(0.5), sleep=lambda s: None) == "failed"


def test_slowdown_multiplies_brew_time():
    r = fakeredis.FakeRedis(decode_responses=True)
    make_order(r, "latte")
    r.set("config:slowdown", 4)
    slept = []
    worker.process_one(r, "abc", rng=FixedRng(0.99), sleep=slept.append)
    assert slept == [16.0]  # latte minimum 4s x 4


def test_missing_order_is_ignored():
    r = fakeredis.FakeRedis(decode_responses=True)
    assert worker.process_one(r, "ghost", sleep=lambda s: None) is None
