# Broker Connectivity Preflights — Read-only Integration Foundations

**TradeBridge Pro v0.2 groundwork** introduces two opt-in commands:

1. **IBKR Client Portal Gateway:** issue one documented **GET** request to `/v1/api/portfolio/accounts` on an *authenticated local HTTPS Gateway*. Return masked identifiers for paper/demo accounts only.
2. **MetaTrader 5:** inspect the **already logged-in demo terminal** using `MetaTrader5.initialize()`, `account_info()`, `terminal_info()`, then `shutdown()`. A real account is explicitly rejected.

These are **read-only connectivity diagnostics, not trading adapters**. They do not route a TradingView signal to IBKR, MT5 or any live exchange. Their source and offline tests are available at [preflight.py](../src/tradebridge/preflight.py) and [test_preflight.py](../tests/test_preflight.py).

## Important distinctions

| Capability | Implemented | Independently connected to account? |
| --- | --- | --- |
| IBKR local HTTPS read-only account probe | Yes | **No** — needs your running authenticated Gateway |
| MT5 local demo account and terminal probe | Yes | **No** — needs your Windows terminal and demo login |
| IBKR/MT5 order submission, acknowledgements, fills, reconciliations | **No** | Not available |
| Existing `SIM_IBKR`, `SIM_MT5`, `SIM_CEX` router | Yes, simulation | Mock data only |

**No passwords, tokens, funded accounts, or private keys should be added to the repository or sent in chat.**

## Option A: IBKR Client Portal Gateway — account visibility only

1. Install and start the IBKR Client Portal Gateway **locally** according to IBKR's own documentation; authenticate via the Gateway's approved flow.
2. Make sure your IBKR paper account is accessible. The command refuses responses containing only live accounts.
3. The probe requires **HTTPS with normal certificate verification**. IBKR's stock Gateway can ship with a placeholder/self-signed certificate; configure a trusted local certificate and a suitable CA bundle. **Do not disable SSL verification or expose the Gateway on a public interface.**
4. Run:

```bash
# macOS / Linux
export TB_ENABLE_READONLY_PREFLIGHT=YES
export TB_IBKR_GATEWAY_URL=https://127.0.0.1:5000/v1/api
export TB_IBKR_CA_BUNDLE=/absolute/path/to/trusted-ca.pem
python -m tradebridge.preflight --provider ibkr
```

`TB_IBKR_CA_BUNDLE` is optional **only** if the Gateway's HTTPS certificate is already trusted by your system. The URL validator permits HTTPS on loopback only, ending in `/v1/api`. Authentication is handled by your already running Gateway session. The code sends no API key or password to IBKR.

Expected structure **only when actually connected**:

```json
{
  "provider": "IBKR_CLIENT_PORTAL",
  "status": "READ_ONLY_PAPER_ACCOUNT_VISIBLE",
  "paper_accounts": [{"masked_account": "••••5678", "currency": "USD"}],
  "orders_enabled": false
}
```

The account identifier shown is fictional and purely illustrative. If there is no session, a TLS trust issue, or no paper account, the command reports `NOT_VERIFIED`.

Official reference: [IBKR GET /portfolio/accounts](https://www.interactivebrokers.com/docs/web-api/v1/endpoints/portfolio/portfolio-accounts); [IBKR Web API sessions](https://www.interactivebrokers.com/docs/web-api/authentication/trading).

## Option B: MetaTrader 5 — demo account visibility only

1. On a Windows PC with the **official MetaTrader 5 terminal**, log into a **demo account** through the terminal interface.
2. Install the Python integration package on that machine: `python -m pip install MetaTrader5`.
3. Enable the probe **only for this execution** and run it:

```powershell
$env:TB_ENABLE_READONLY_PREFLIGHT="YES"
# Optional: $env:TB_MT5_TERMINAL_PATH="C:\Program Files\MetaTrader 5\terminal64.exe"
python -m tradebridge.preflight --provider mt5
```

If a live-funded MT5 account is currently logged in, the command refuses to return account details; it never executes `order_send`, `login` or any other trade-producing call. It masks account numbers and prints no balance/equity values.

Official references: [MT5 initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py), [MT5 account_info](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py), [MT5 terminal_info](https://www.mql5.com/en/docs/python_metatrader5/mt5terminalinfo_py).

## Test the preflight code without brokers

```bash
pip install -e ".[dev]"
pytest -q tests/test_preflight.py
```

The test file uses mock responses, checks that the IBKR request is **GET-only over HTTPS**, rejects non-local URLs and live-only account responses, verifies MT5 demo-only behavior, confirms `order_send` is not called, and ensures terminal shutdown runs on failures.

**Offline unit tests passing does not prove a real IBKR or MT5 connection.** An end-to-end connection is a separate, explicit acceptance milestone.

## Future broker-demo acceptance gates

- Capture timestamped **redacted** session and account-read evidence from your own local machine.
- Verify instrument metadata and contract/lot mapping separately for each provider.
- Add broker paper/demo order adapters only with explicit account/environment allowlisting and independent confirmation.
- Test broker failures, restarts, partial fills, reconciliation, and maximum-loss protections in an approved demo environment.
- Re-assess security and deployment before considering any funded-account functionality.

Developed by **Raja Channa · NextGen Tech Solutions** — https://nextgentechdev.com.
