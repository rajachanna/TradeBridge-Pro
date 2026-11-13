"""Reproducible, network-free portfolio demonstration.

Run: python scripts/demo.py
Needs: pip install -e ".[dev]"
No real broker API calls and no persistent credentials.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from fastapi.testclient import TestClient

from tradebridge.api import create_app
from tradebridge.config import Settings


def show(name: str, response):
    print(f"\n{name} — HTTP {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return response


def main():
    with TemporaryDirectory(prefix="tradebridge-demo-") as temp_dir:
        settings = Settings(
            webhook_secret="temporary-example-webhook-secret-12345",
            operator_key="temporary-example-operator-key-67890",
            db_path=Path(temp_dir) / "demo.sqlite",
        )
        client = TestClient(create_app(settings))
        headers = {"X-API-Key": settings.operator_key}

        def alert(signal_id, side="BUY", price="65000"):
            return {
                "secret": settings.webhook_secret,
                "signal_id": signal_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "venue": "SIM_CEX",
                "symbol": "BTCUSDT",
                "side": side,
                "quantity": "0.01",
                "price": price,
                "strategy": "showcase_demo",
            }

        print("TradeBridge Pro — SIMULATED ONLY / NO BROKER CONNECTION")
        first = alert("demo-buy-001")
        show("1. First simulated buy", client.post("/api/webhook", json=first))
        show("2. Repeated ID (idempotent)", client.post("/api/webhook", json=first))
        changed = {**first, "price": "70000"}
        show("3. Same ID, different instructions (conflict)", client.post("/api/webhook", json=changed))
        show("4. Operator halt", client.post("/api/control/halt", headers=headers))
        show("5. New trade blocked during halt", client.post("/api/webhook", json=alert("demo-blocked-002")))
        show("6. Operator resume", client.post("/api/control/resume", headers=headers))
        show("7. Simulated sell", client.post("/api/webhook", json=alert("demo-sell-003", "SELL", "66000")))
        portfolio = show("8. Final fictional portfolio", client.get("/api/portfolio", headers=headers)).json()
        balances = {x["venue"]: Decimal(x["cash"]) for x in portfolio["balances"]}
        assert balances["SIM_CEX"] == Decimal("10010")
        print("\nPASS — demo round trip and isolated paper ledger verified (no fees/slippage).")


if __name__ == "__main__":
    main()
