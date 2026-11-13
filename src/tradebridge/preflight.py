"""Opt-in, read-only broker connectivity preflights (never routes orders).

IBKR: GET a loopback Client Portal Gateway's /portfolio/accounts endpoint.
MT5: connect to an existing terminal; inspect account and terminal info; shut down.

No credentials, live trading or order placement is implemented here.
The real endpoints require a configured, authenticated local gateway/terminal.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import ssl
from urllib import error, parse, request
from typing import Any, Callable


class PreflightError(RuntimeError):
    """Safe, deliberately non-sensitive error for an unsuccessful preflight."""


def _mask(value: str) -> str:
    """Never expose complete account identifiers in diagnostic output."""
    identifier = str(value)
    return "••••" + identifier[-4:] if identifier else "unknown"


def _gateway_url(base_url: str) -> str:
    """Refuse non-local or non-HTTPS targets to avoid arbitrary outbound requests."""
    try:
        parsed = parse.urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise PreflightError("Invalid local IBKR Gateway URL.") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1/api"
        or port is None
    ):
        raise PreflightError(
            "Only a local HTTPS IBKR Client Portal Gateway URL ending in /v1/api is permitted."
        )
    return base_url.rstrip("/") + "/portfolio/accounts"


def ibkr_paper_preflight(
    *,
    gateway_url: str = "https://127.0.0.1:5000/v1/api",
    ca_bundle: str | None = None,
    opener: Callable[..., Any] | None = None,
    timeout: float = 6.0,
) -> dict:
    """Use the documented read-only IBKR Web API portfolio/accounts endpoint.

    TLS certificate verification is REQUIRED. For a stock Gateway's placeholder
    certificate, configure a locally trusted replacement and a CA bundle.
    No request is made to an /iserver endpoint and no POST is ever sent.
    """
    url = _gateway_url(gateway_url)
    if timeout <= 0 or timeout > 30:
        raise PreflightError("Timeout must be between 0 and 30 seconds.")
    try:
        context = ssl.create_default_context(cafile=ca_bundle)
    except (OSError, ssl.SSLError) as exc:
        raise PreflightError("Could not load trusted IBKR Gateway certificate bundle.") from exc
    get = request.Request(url, method="GET", headers={"Accept": "application/json"})
    open_url = opener or request.urlopen
    try:
        with open_url(get, timeout=timeout, context=context) as response:
            payload = json.load(response)
    except (error.HTTPError, error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise PreflightError(
            "IBKR Gateway read-only query failed. Check the local gateway, authentication and TLS trust."
        ) from exc

    if not isinstance(payload, list):
        raise PreflightError("IBKR Gateway returned an unexpected accounts response.")
    demo_accounts: list[dict] = []
    for account in payload:
        if not isinstance(account, dict):
            continue
        raw = str(account.get("accountId") or account.get("id") or "")
        kind = str(account.get("type") or "").upper()
        if raw.startswith("DU") or kind in {"DEMO", "PAPER"}:
            demo_accounts.append({
                "masked_account": _mask(raw),
                "currency": str(account.get("currency") or "unknown")[:10],
            })

    if not demo_accounts:
        raise PreflightError("No paper/demo IBKR account returned; live accounts are not accepted.")
    return {
        "provider": "IBKR_CLIENT_PORTAL",
        "status": "READ_ONLY_PAPER_ACCOUNT_VISIBLE",
        "paper_accounts": demo_accounts,
        "orders_enabled": False,
    }


def mt5_demo_preflight(*, mt5_module: Any | None = None, terminal_path: str | None = None) -> dict:
    """Read the logged-in MT5 account and terminal. Reject live accounts.

    The official MetaTrader5 Python library needs a running local terminal
    (typically Windows). No order_send, login or password parameters are used.
    """
    if mt5_module is None:
        try:
            mt5_module = importlib.import_module("MetaTrader5")
        except ImportError as exc:
            raise PreflightError(
                "MetaTrader5 Python package unavailable. Run the probe on Windows with an MT5 demo terminal."
            ) from exc

    initialized = False
    try:
        try:
            initialized = bool(mt5_module.initialize(terminal_path)) if terminal_path else bool(mt5_module.initialize())
        except Exception as exc:
            raise PreflightError("MT5 terminal initialization failed.") from exc
        if not initialized:
            raise PreflightError("MT5 terminal initialization failed; check the local demo terminal.")

        account = mt5_module.account_info()
        terminal = mt5_module.terminal_info()
        if account is None or terminal is None:
            raise PreflightError("MT5 terminal did not return an account and terminal status.")
        if not bool(getattr(terminal, "connected", False)):
            raise PreflightError("MT5 terminal is not currently connected.")
        demo_value = getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", 0)
        if getattr(account, "trade_mode", None) != demo_value:
            raise PreflightError("Logged-in MT5 account is not DEMO; live account details will not be returned.")
        return {
            "provider": "METATRADER5",
            "status": "READ_ONLY_DEMO_ACCOUNT_VISIBLE",
            "masked_account": _mask(str(getattr(account, "login", ""))),
            "currency": str(getattr(account, "currency", "unknown"))[:10],
            "terminal_connected": True,
            "orders_enabled": False,
        }
    except PreflightError:
        raise
    except Exception as exc:
        raise PreflightError("MT5 read-only account/terminal check failed.") from exc
    finally:
        try:
            mt5_module.shutdown()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only IBKR/MT5 demo account preflight (no orders).")
    parser.add_argument("--provider", choices=("ibkr", "mt5"), required=True)
    args = parser.parse_args(argv)

    if os.environ.get("TB_ENABLE_READONLY_PREFLIGHT") != "YES":
        parser.exit(2, "Preflight disabled. Explicitly set TB_ENABLE_READONLY_PREFLIGHT=YES.\n")
    try:
        if args.provider == "ibkr":
            result = ibkr_paper_preflight(
                gateway_url=os.environ.get("TB_IBKR_GATEWAY_URL", "https://127.0.0.1:5000/v1/api"),
                ca_bundle=os.environ.get("TB_IBKR_CA_BUNDLE") or None,
            )
        else:
            result = mt5_demo_preflight(terminal_path=os.environ.get("TB_MT5_TERMINAL_PATH") or None)
    except PreflightError as exc:
        print(json.dumps({"status": "NOT_VERIFIED", "provider": args.provider, "reason": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
