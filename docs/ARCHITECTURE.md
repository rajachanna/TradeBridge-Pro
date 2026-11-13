# Architecture: TradingView-style signals to mock execution

TradeBridge Pro v0.1 is a **simulation system**. The names SIM_IBKR, SIM_MT5 and SIM_CEX are labels for isolated, fictional accounts, not official APIs.

\`\`\`mermaid
flowchart LR
    A["Strategy alert (JSON)"] --> B["FastAPI /api/webhook"]
    B --> C{"Secret, timestamp, schema"}
    C -->|invalid| X["HTTP 401 or 422"]
    C -->|valid| D{"SQLite idempotency + risk checks"}
    D -->|conflict or rejected| Y["HTTP 409 or 422 + audit event"]
    D -->|approved| E["SIMULATED fill"]
    E --> F[("Balances / Positions / Orders / Events")]
    F --> G["Operator API"]
    G --> H["Local Dashboard"]
    I["Operator halt/resume"] --> D
\`\`\`

## What is implemented

- **Ingress:** Pydantic input validation, JSON secret and timestamp freshness check.
- **Isolation:** each simulated venue has fictional cash and holdings, starting at USD 10,000.
- **Idempotency:** duplicate signal IDs with unchanged execution details return \`DUPLICATE\`; changed details return HTTP 409.
- **Transaction:** \`BEGIN IMMEDIATE\` and a unique signal ID key protect SQLite state changes from straightforward double-application.
- **Risk checks:** order notional, per-symbol exposure, aggregate gross exposure using **last alert prices**, number of positions, cash, daily **realized** loss and manual emergency halt.
- **Observability:** read-only orders, position and audit endpoints guarded by a second API key.
- **Simulation only:** fills occur immediately at *alert-provided* prices. There is no fee, slippage, market data, partial fill, broker acknowledgement or position reconciliation model.

## Scope boundaries

The project currently models quantities as *units of fictional, USD-notional assets*. **XAUUSD and EURUSD are not modeled as actual MT5 lots, contract sizes or currency conversion rules.** Similarly, SIM_IBKR does not verify actual stock market quotes or order status.

Do not use these mock responses as a trading strategy backtest or claim broker-confirmed execution. Nothing here transmits orders to a brokerage account.

## Next integration gates

1. Typed async adapter contract with **read-only** discovery against IBKR paper, MT5 demo and CEX sandbox environments.
2. Broker-native symbol/contract resolution, margin/lot-size validation and market-calendar checks.
3. Explicit order routing approval, per-adapter credentials and paper-environment lockout.
4. Transport retries and deduplication, broker acknowledgement events, partial fills, cancel/replace and reconciliation.
5. Security assessment, operator controls, monitoring, integration tests and acceptance reports before any funded trading design.

Real venue status must remain **planned** until verified against each provider's account and API.
