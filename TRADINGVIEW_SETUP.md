# TradingView → Crypto Hunters setup

## Deploy

Start command:

```bash
python launcher.py
```

The package runs:

- Streamlit web app on port 8501
- TradingView webhook receiver on port 8000
- Health endpoint: `/health`
- TradingView webhook endpoint: `/webhook/tradingview`

Your hosting service must expose the webhook endpoint publicly over HTTPS.

## Secret

Set this environment variable on the host:

```text
TRADINGVIEW_WEBHOOK_SECRET=a-long-random-private-string
```

Use the same value for **Webhook secret** in the Pine Script settings.

## TradingView

1. Open the exact TradingView contract you want, preferably the KCEX perpetual chart when available.
2. Open Pine Editor.
3. Paste `Crypto_Hunters_TV_Bridge.pine`.
4. Save and add it to the chart.
5. Create an alert.
6. Condition: `Crypto Hunters TV Bridge v1`.
7. Select `Any alert() function call`.
8. Enable webhook URL and enter:

```text
https://YOUR-WEBHOOK-HOST/webhook/tradingview
```

The Pine Script generates the JSON alert body.

## Important

A TradingView alert watches the symbol and timeframe where that alert was created. One alert does not scan every market worldwide. Start with a focused KCEX watchlist, then expand the alert list.
