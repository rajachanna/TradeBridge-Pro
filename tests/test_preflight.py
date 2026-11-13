"""All preflight tests are offline. No real broker credentials or connection needed."""
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tradebridge.preflight import (
    PreflightError,
    _gateway_url,
    ibkr_paper_preflight,
    mt5_demo_preflight,
    main,
)


class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def fake_gateway(payload):
    observed = []

    def opener(req, **kwargs):
        observed.append((req, kwargs))
        return FakeHTTPResponse(json.dumps(payload).encode())

    return opener, observed


def test_ibkr_get_request_and_masks_demo_id():
    opener, calls = fake_gateway([
        {"accountId": "U777777", "type": "INDIVIDUAL", "currency": "USD"},
        {"accountId": "DU12345678", "type": "DEMO", "currency": "USD"},
    ])
    result = ibkr_paper_preflight(opener=opener)
    assert result["status"] == "READ_ONLY_PAPER_ACCOUNT_VISIBLE"
    assert result["orders_enabled"] is False
    assert len(result["paper_accounts"]) == 1
    assert result["paper_accounts"][0]["masked_account"].endswith("5678")
    assert "DU12345678" not in str(result)
    req, options = calls[0]
    assert req.get_method() == "GET"
    assert req.full_url == "https://127.0.0.1:5000/v1/api/portfolio/accounts"
    assert options["timeout"] == 6
    assert options["context"].verify_mode != 0


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:5000/v1/api",
    "https://ibkr.example.com/v1/api",
    "https://localhost:5000/iserver",
    "https://localhost:5000/v1/api?x=1",
    "https://evil.test@localhost:5000/v1/api",
    "https://localhost/v1/api",
    "javascript:alert(1)",
])
def test_ibkr_url_validation_prevents_remote_requests(url):
    with pytest.raises(PreflightError):
        _gateway_url(url)


def test_ibkr_rejects_live_only_accounts():
    opener, _ = fake_gateway([{"accountId": "U1111111", "type": "INDIVIDUAL"}])
    with pytest.raises(PreflightError, match="No paper/demo"):
        ibkr_paper_preflight(opener=opener)


def test_ibkr_rejects_unexpected_response():
    opener, _ = fake_gateway({"message": "login required"})
    with pytest.raises(PreflightError, match="unexpected"):
        ibkr_paper_preflight(opener=opener)


def test_mt5_demo_status_masked_and_shutdown():
    mt5 = SimpleNamespace(
        ACCOUNT_TRADE_MODE_DEMO=0,
        initialize=Mock(return_value=True),
        account_info=Mock(return_value=SimpleNamespace(login=12345678, trade_mode=0, currency="USD")),
        terminal_info=Mock(return_value=SimpleNamespace(connected=True)),
        shutdown=Mock(),
        order_send=Mock(),
    )
    result = mt5_demo_preflight(mt5_module=mt5)
    assert result["masked_account"].endswith("5678")
    assert "12345678" not in str(result)
    assert result["orders_enabled"] is False
    mt5.order_send.assert_not_called()
    mt5.shutdown.assert_called_once()


def test_mt5_live_account_rejected_even_for_read_only():
    mt5 = SimpleNamespace(
        ACCOUNT_TRADE_MODE_DEMO=0,
        initialize=Mock(return_value=True),
        account_info=Mock(return_value=SimpleNamespace(login=987654, trade_mode=2)),
        terminal_info=Mock(return_value=SimpleNamespace(connected=True)),
        shutdown=Mock(),
    )
    with pytest.raises(PreflightError, match="not DEMO"):
        mt5_demo_preflight(mt5_module=mt5)
    mt5.shutdown.assert_called_once()


def test_mt5_shutdown_on_terminal_error():
    mt5 = SimpleNamespace(
        initialize=Mock(return_value=False),
        shutdown=Mock(),
    )
    with pytest.raises(PreflightError, match="initialization failed"):
        mt5_demo_preflight(mt5_module=mt5)
    mt5.shutdown.assert_called_once()


def test_mt5_disconnected_terminal_rejected():
    mt5 = SimpleNamespace(
        initialize=Mock(return_value=True),
        account_info=Mock(return_value=SimpleNamespace(trade_mode=0)),
        terminal_info=Mock(return_value=SimpleNamespace(connected=False)),
        shutdown=Mock(),
    )
    with pytest.raises(PreflightError, match="not currently connected"):
        mt5_demo_preflight(mt5_module=mt5)


def test_cli_fails_closed_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("TB_ENABLE_READONLY_PREFLIGHT", raising=False)
    with pytest.raises(SystemExit) as exc:
        main(["--provider", "ibkr"])
    assert exc.value.code == 2


def test_cli_preflight_success_with_fake_gateway(monkeypatch, capsys):
    monkeypatch.setenv("TB_ENABLE_READONLY_PREFLIGHT", "YES")
    monkeypatch.setattr(
        "tradebridge.preflight.ibkr_paper_preflight",
        lambda **_kwargs: {"status": "READ_ONLY_PAPER_ACCOUNT_VISIBLE", "orders_enabled": False},
    )
    assert main(["--provider", "ibkr"]) == 0
    assert json.loads(capsys.readouterr().out)["orders_enabled"] is False
