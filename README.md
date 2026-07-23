# Crypto Hunters 4.0 — Persistent Trade Coach

## What changed

- The selected coin, LONG/SHORT direction, entry price, stop, target, trailing settings, and notification settings are saved in SQLite.
- Refreshing the browser or opening it on another device loads the same saved trade.
- `monitor.py` checks the active trade without needing the browser page open.
- Urgent alerts can be sent through Telegram or Twilio SMS.
- Optional periodic status messages act like a commentator.

## Run locally

```bash
pip install -r requirements.txt
python launcher.py
```

Using `streamlit run app.py` alone displays the app, but does not start the separate background monitor.

## Streamlit Community Cloud limitation

Community Cloud can hibernate an inactive app. That means it cannot guarantee uninterrupted alerts while nobody has the page open. Use an always-on server or worker for unattended monitoring.

## Environment variables

Telegram:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Twilio SMS:

```text
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER
ALERT_PHONE_NUMBER
```

Phone numbers must use E.164 format, such as `+12025550123`.

## Start command for an always-on host

```text
python launcher.py
```


## Version 4.1 live-refresh fix

This version fixes the "Waiting for first check" screen by:

- Starting the background monitor automatically from `app.py`
- Refreshing the Trade Coach page automatically at the saved interval
- Showing whether the monitor thread is running
- Showing the age of the last successful market update
- Showing live commentary and the reason for the current action

For Streamlit Community Cloud, set `app.py` as the main file and redeploy after replacing all project files.

The commentary is currently rules-based and grounded in the indicators. This is intentionally safer than allowing a language model to invent market predictions. An optional language-model layer can later rewrite the same verified data into more conversational wording without changing the trading rules.


## Version 4.2 native refresh fix

The Trade Coach now uses Streamlit's native fragment refresh.

Every 15 seconds while the page is open it:

1. Requests fresh Bitget data.
2. Recalculates the live position.
3. Updates the saved record.
4. Redraws price, P/L, peak move, action, and commentary.

The external auto-refresh component was removed. AI commentary is intentionally postponed until the live data loop is proven reliable.

## Version 5.1: Behind-the-chart Market Intelligence

Open the **Market Intelligence** tab and enter a Bitunix USDT perpetual contract such as `BTCUSDT`.
The engine reads order-book imbalance, spread, funding, basis, recent directional volume pressure, volume impulse, and range expansion. It stores readings so the app can chart whether long pressure or short pressure is strengthening over time.

This module does not promise direction. Visible orders can be canceled, funding can remain extreme, and high pressure can reverse through liquidation. Use it as independent confirmation alongside TradingView structure and risk controls.

## Version 5.2 — Scanner-to-Coach workflow

- Adjustable EMA fast/middle/slow values in both the scanner and Trade Coach.
- RSI/MACD alignment added to scanner grading.
- Scanner results can be selected and sent directly to the persistent Trade Coach.
- Manually entered USDT contracts use the same grading model and are remembered after saving.
- The live Trade Coach records a 15-second history trail with price, P/L, scanner score, micro score, bullish pressure, bearish pressure, action, and reason.
- Existing market-intelligence and TradingView webhook features remain included.

## Version 5.3 interface and symbol-safety update

- Normalizes KCEX-style entries such as `DEXE/USDT`, `DEXE-USDT`, and `DEXE_USDT` to the Bitget contract format.
- Tests that a symbol exists on Bitget and has enough candle history before monitoring starts.
- Shows the current market-data source and a visible LIVE/WAITING connection status.
- Blocks obviously mismatched entry prices when they are more than 25% from the live contract price.
- Uses compact action labels so critical messages fit: STOP EXIT, TARGET HIT, TRAILING EXIT, REVERSAL EXIT, PROTECT PROFIT, HOLD PROFIT, and MONITOR.
- Keeps prices and percentages large while allowing the action message to wrap without ellipses.
- Shows take-profit, trailing activation, and giveback status separately.
