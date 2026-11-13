from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from tradebridge.api import create_app
from tradebridge.config import Settings


OPERATOR = {"X-API-Key": "sample-operator-key-xyz-123456"}
WEBHOOK_SECRET = "sample-webhook-secret-xyz-987654"


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        webhook_secret=WEBHOOK_SECRET,
        operator_key=OPERATOR["X-API-Key"],
        db_path=tmp_path / "test.sqlite",
    )
    return TestClient(create_app(settings))


def signal(**overrides):
    value = {
        "secret": WEBHOOK_SECRET,
        "signal_id": "demo-alert-0001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "venue": "SIM_CEX",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "0.01",
        "price": "65000",
        "strategy": "test_strategy",
    }
    value.update(overrides)
    return value


def send(client, **overrides):
    return client.post("/api/webhook", json=signal(**overrides))


def test_health_and_venues(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "SIMULATED_ONLY"
    venues = client.get("/api/venues").json()
    assert "SIM_IBKR" in venues["venues"]
    assert "SIM_MT5" in venues["venues"]
    assert "SIM_CEX" in venues["venues"]


def test_operator_auth(client):
    assert client.get("/api/portfolio").status_code == 401
    assert client.get("/api/orders").status_code == 401
    assert client.post("/api/control/halt").status_code == 401
    assert client.get("/api/portfolio", headers=OPERATOR).status_code == 200


def test_webhook_auth(client):
    assert send(client, secret="not-the-correct-secret").status_code == 401


def test_buy_and_duplicate(client):
    accepted = send(client)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "SIMULATED_FILLED"

    repeat = send(client)
    assert repeat.status_code == 200
    assert repeat.json()["status"] == "DUPLICATE"

    state = client.get("/api/portfolio", headers=OPERATOR).json()
    assert Decimal(next(x["cash"] for x in state["balances"] if x["venue"] == "SIM_CEX")) == Decimal("9350")
    assert len(state["positions"]) == 1
    assert len(client.get("/api/orders", headers=OPERATOR).json()["orders"]) == 1


def test_same_signal_id_with_changed_payload_is_conflict(client):
    assert send(client).status_code == 200
    response = send(client, price="66000")
    assert response.status_code == 409
    assert len(client.get("/api/orders", headers=OPERATOR).json()["orders"]) == 1


def test_sell_and_realized_pnl(client):
    assert send(client).status_code == 200
    r = send(client, signal_id="demo-alert-0002", side="SELL", price="66000")
    assert r.status_code == 200
    assert Decimal(r.json()["realized_pnl_usd"]) == Decimal("10")
    state = client.get("/api/portfolio", headers=OPERATOR).json()
    assert not state["positions"]
    assert Decimal(next(x["cash"] for x in state["balances"] if x["venue"] == "SIM_CEX")) == Decimal("10010")


def test_separate_mock_venue_accounts(client):
    assert send(client).status_code == 200
    assert send(client, venue="SIM_IBKR", symbol="AAPL", quantity="2", price="200", signal_id="ibkr-0001").status_code == 200
    state = client.get("/api/portfolio", headers=OPERATOR).json()
    balances = {x["venue"]: Decimal(x["cash"]) for x in state["balances"]}
    assert balances["SIM_CEX"] == Decimal("9350")
    assert balances["SIM_IBKR"] == Decimal("9600")
    assert balances["SIM_MT5"] == Decimal("10000")
    assert len(state["positions"]) == 2


@pytest.mark.parametrize("overrides", [
    {"symbol": "DOGEUSDT"},
    {"venue": "SIM_MT5", "symbol": "BTCUSDT"},
    {"quantity": "0"},
    {"price": "-1"},
    {"price": "NaN"},
    {"side": "HOLD"},
    {"quantity": "1"},
])
def test_invalid_or_risky_signal(client, overrides):
    assert send(client, **overrides).status_code == 422


def test_sell_without_holdings_is_blocked(client):
    assert send(client, side="SELL").status_code == 422
    assert client.get("/api/orders", headers=OPERATOR).json()["orders"] == []


def test_stale_future_and_timezone_missing(client):
    now = datetime.now(timezone.utc)
    assert send(client, timestamp=(now - timedelta(minutes=5)).isoformat()).status_code == 422
    assert send(client, timestamp=(now + timedelta(minutes=5)).isoformat()).status_code == 422
    assert send(client, timestamp=now.replace(tzinfo=None).isoformat()).status_code == 422


def test_halt_and_resume(client):
    assert client.post("/api/control/halt", headers=OPERATOR).json()["halted"] is True
    assert send(client).status_code == 422
    assert client.post("/api/control/resume", headers=OPERATOR).json()["halted"] is False
    assert send(client).status_code == 200


def test_realized_daily_loss_blocks_new_buys(client):
    assert send(client, quantity="0.03").status_code == 200
    assert send(client, signal_id="demo-alert-0002", side="SELL",
                quantity="0.03", price="1000").status_code == 200
    r = send(client, signal_id="demo-alert-0003")
    assert r.status_code == 422
    assert "Daily realized-loss" in r.text


def test_events_do_not_include_shared_secret(client):
    assert send(client, symbol="DOGEUSDT").status_code == 422
    response = client.get("/api/events", headers=OPERATOR)
    assert response.status_code == 200
    assert "REJECTED" in response.text
    assert WEBHOOK_SECRET not in response.text


def test_documentation_and_dashboard(client):
    assert client.get("/docs").status_code == 200
    page = client.get("/")
    assert page.status_code == 200
    assert "SIMULATION ONLY" in page.text
