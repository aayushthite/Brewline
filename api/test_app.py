import fakeredis
import pytest
from fastapi.testclient import TestClient

import app as api


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(api, "r", fakeredis.FakeRedis(decode_responses=True))
    return TestClient(api.app)


def test_menu_lists_drinks(client):
    drinks = {m["drink"] for m in client.get("/api/menu").json()}
    assert {"espresso", "latte"} <= drinks


def test_create_order_queues_it(client):
    res = client.post("/api/orders", json={"drink": "latte", "customer": "asha"})
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "queued" and body["position"] == 1
    assert client.get(f"/api/orders/{body['id']}").json()["drink"] == "latte"
    assert len(client.get("/api/orders/recent").json()) == 1


def test_unknown_drink_rejected(client):
    assert client.post("/api/orders", json={"drink": "soup"}).status_code == 400


def test_missing_order_is_404(client):
    assert client.get("/api/orders/nope").status_code == 404


def test_chaos_is_clamped(client):
    res = client.post("/api/chaos", json={"slowdown": 99, "fail_rate": 5}).json()
    assert res == {"slowdown": 10.0, "fail_rate": 1.0}


def test_metrics_expose_business_counters(client):
    client.post("/api/orders", json={"drink": "matcha"})
    text = client.get("/metrics").text
    assert 'brewline_orders_created_total{drink="matcha"}' in text
    assert "brewline_queue_depth" in text
    assert "brewline_http_request_duration_seconds_bucket" in text
