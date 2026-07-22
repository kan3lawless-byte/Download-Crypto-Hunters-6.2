from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
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

def init_intelligence_tables() -> None:
    with connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS market_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT,
            regime TEXT,
            long_score REAL,
            short_score REAL,
            payload_json TEXT NOT NULL
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mi_symbol_time ON market_intelligence(symbol, created_at DESC)")

def save_intelligence(payload: dict[str, Any]) -> int:
    init_intelligence_tables()
    with connection() as conn:
        cur = conn.execute("""
        INSERT INTO market_intelligence(created_at, symbol, direction, regime, long_score, short_score, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(), payload.get("symbol"), payload.get("direction"), payload.get("regime"),
            payload.get("long_pressure_score"), payload.get("short_pressure_score"), json.dumps(payload)
        ))
        return int(cur.lastrowid)

def recent_intelligence(symbol: str, limit: int = 60) -> list[dict[str, Any]]:
    init_intelligence_tables()
    with connection() as conn:
        rows = conn.execute("""
        SELECT * FROM market_intelligence WHERE symbol=? ORDER BY created_at DESC LIMIT ?
        """, (symbol, limit)).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        try:
            item.update(json.loads(item.pop("payload_json")))
        except Exception:
            pass
        result.append(item)
    return result
