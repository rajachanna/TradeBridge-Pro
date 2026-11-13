# Security and deployment boundaries

**TradeBridge Pro is an experimental locally run simulator, not a production platform.**

- Keep \`.env\` out of Git. Use different, strong \`TB_WEBHOOK_SECRET\` and \`TB_OPERATOR_KEY\` values; rotate them if disclosed.
- Don't send broker passwords, API trading secrets or wallet private keys through TradingView webhooks.
- TradingView webhooks are JSON POST requests. Public access needs HTTPS, network allowlists, secret management and rate limiting. The published Docker setup binds to localhost only.
- The incoming alert price is unverified; a hostile sender who knows the secret can manipulate fictional balances. **Never connect this simulator directly to funded orders.**
- The dashboard API key stays in browser memory and is never intentionally stored in localStorage.
- The \`HALT\` button blocks new simulated orders; it does not cancel or manage external broker positions.
- Daily loss uses *realized simulated P&L only*. It cannot detect mark-to-market risk or guarantee loss limits.
- SQLite is a local demonstration store; deployment at scale needs backup/restore, transactional migrations, concurrency testing, monitoring, and stronger authentication.
- Broker-specific trading details (units vs lots, commissions, quotes, margin, fills, time-in-force, calendars) are intentionally not modeled.
- To report issues privately, use https://nextgentechdev.com and don't publicly paste credentials.

The code does not include a hidden live-trading option or call any broker API.
