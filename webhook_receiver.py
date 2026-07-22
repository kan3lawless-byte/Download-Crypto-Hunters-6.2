from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException, Request
from tv_store import init_tv_tables, save_signal
from market_intelligence import build_market_intelligence
from intelligence_store import init_intelligence_tables, save_intelligence
app = FastAPI(title="Crypto Hunters TradingView Webhook")
init_tv_tables()
init_intelligence_tables()
@app.get("/health")
def health():
    return {"ok": True, "service": "crypto-hunters-webhook"}
@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON") from exc
    expected = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
    supplied = str(payload.get("secret", "")).strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")
    if supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    required = ["symbol", "direction", "signal", "score", "price"]
    missing = [name for name in required if payload.get(name) in (None, "")]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing fields: {', '.join(missing)}")
    signal_id = save_signal(payload)
    return {"ok": True, "signal_id": signal_id}
