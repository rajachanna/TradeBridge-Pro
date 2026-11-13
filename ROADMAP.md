# Roadmap — TradeBridge Pro

## ✅ v0.1 — simulated order-routing prototype

- TradingView-style JSON webhook endpoint
- Timestamp and secret validation
- Distinct mock venues SIM_IBKR / SIM_MT5 / SIM_CEX
- Strict symbol allowlists, cash and exposure checks
- SQLite order idempotency + conflict detection
- Halt / resume controls and audit events
- Responsive operator dashboard and API tests

## ✅ v0.2 groundwork — read-only broker connectivity (code and offline tests)

- IBKR local Client Portal Gateway paper-account listing via GET-only endpoint
- MT5 already-logged-in DEMO terminal account/connection checks
- TLS verification, local-only IBKR target, masked account identifiers and explicit CLI opt-in
- Offline fake-connector security tests; **real paper/demo connectivity not yet verified**

## 🔲 v0.2 — harden the simulator

- Request rate limiting and HTTPS deployment guidance
- Price-source separation, contract/lot specifications, cost/slippage simulation
- Richer strategy routing rules and expiry/replay controls
- Concurrency/load tests, database migration and telemetry

## 🔲 v0.3 — independently validated external adapters

- IBKR paper-account connectivity, order IDs and broker confirmation states
- MT5 demo-account connectivity, symbol/lot sizing, rejection handling and account confirmation
- CEX supported sandbox APIs, order acknowledgement and reconciliation
- Broker contract tests for network failures and partial fills

## 🔲 Later

- DEX **simulation first**, quote validation and transaction/chain-risk modelling
- Backtesting, alerts, advanced risk analytics and deployment hardening

**All real IBKR, MT5, CEX and DEX integrations are planned; none ship in v0.1.**
