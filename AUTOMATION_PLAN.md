# Crypto Hunters 6.0 — Safe Automation Plan

## Recommended first venue

Use Coinbase Advanced as the first U.S. execution venue. Begin with spot automation, not leveraged futures, because the current balance is too small to absorb normal futures volatility, fees, liquidation risk, and software mistakes.

Kraken Spot is the backup venue. Both venues support API-based account/order workflows. Live order transmission is intentionally locked in version 6.0.

## Operating modes

1. Paper: Hunter decisions create simulated entries and exits only.
2. Approval required: planned next phase; Hunter prepares an order and the user approves it.
3. Limited live: planned only after paper results pass the required performance and drawdown tests.

## Hard safety rules

- Withdrawal permissions disabled.
- 1× leverage / spot only at launch.
- One position at a time.
- Risk per trade set independently from position size.
- Daily loss shutdown.
- Maximum number of trades per day.
- Minimum Hunter score.
- Kill switch enabled by default.
- Full event log.

## Secrets

Never paste exchange credentials into the source code, UI, or chat. Use deployment secrets/environment variables:

- `COINBASE_API_KEY`
- `COINBASE_API_SECRET`
- `KRAKEN_API_KEY`
- `KRAKEN_API_SECRET`

Version 6.0 detects whether secrets are configured but does not send live orders.
