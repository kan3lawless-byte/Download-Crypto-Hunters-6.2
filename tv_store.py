from __future__ import annotations
import json, os, sqlite3, threading, time
from contextlib import contextmanager
from typing import Any
DB_PATH = os.getenv("CRYPTO_HUNTERS_DB", "crypto_hunters.db")
_LOCK = threading.RLock()
@contextmanager
def connection():
    with _LOCK:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
def init_tv_tables() -> None:
    with connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS tradingview_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, received_at REAL NOT NULL,
            source TEXT, exchange TEXT, symbol TEXT NOT NULL, tickerid TEXT,
            timeframe TEXT, direction TEXT, signal TEXT, score REAL, price REAL,
            rsi REAL, atr_pct REAL, rvol REAL, extension_pct REAL, bar_time INTEGER,
            raw_json TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_received ON tradingview_signals(received_at DESC)")
def save_signal(payload: dict[str, Any]) -> int:
    init_tv_tables()
    with connection() as conn:
        cur = conn.execute("""INSERT INTO tradingview_signals (
            received_at,source,exchange,symbol,tickerid,timeframe,direction,signal,
            score,price,rsi,atr_pct,rvol,extension_pct,bar_time,raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            time.time(), payload.get("source"), payload.get("exchange"),
            payload.get("symbol"), payload.get("tickerid"), payload.get("timeframe"),
            payload.get("direction"), payload.get("signal"), payload.get("score"),
            payload.get("price"), payload.get("rsi"), payload.get("atr_pct"),
            payload.get("rvol"), payload.get("extension_pct"), payload.get("bar_time"),
            json.dumps(payload)))
        return int(cur.lastrowid)
def recent_signals(limit: int = 100) -> list[dict[str, Any]]:
    init_tv_tables()
    with connection() as conn:
        rows = conn.execute("SELECT * FROM tradingview_signals ORDER BY received_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
