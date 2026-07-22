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

def _add_column(conn: sqlite3.Connection, name: str, ddl: str) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(active_trade)").fetchall()}
    if name not in cols:
        conn.execute(f"ALTER TABLE active_trade ADD COLUMN {name} {ddl}")

def init_db() -> None:
    with connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS active_trade (
            id INTEGER PRIMARY KEY CHECK(id=1),
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss_pct REAL NOT NULL DEFAULT 1.0,
            take_profit_pct REAL NOT NULL DEFAULT 2.0,
            trailing_activation_pct REAL NOT NULL DEFAULT 1.0,
            trailing_drawdown_pct REAL NOT NULL DEFAULT 0.5,
            refresh_seconds INTEGER NOT NULL DEFAULT 15,
            status_update_minutes INTEGER NOT NULL DEFAULT 10,
            telegram_enabled INTEGER NOT NULL DEFAULT 0,
            sms_enabled INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            peak_pnl_pct REAL NOT NULL DEFAULT 0,
            last_action TEXT,
            last_alert_at REAL,
            last_status_at REAL,
            last_price REAL,
            last_report_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """)
        _add_column(conn, "ema_fast", "INTEGER NOT NULL DEFAULT 9")
        _add_column(conn, "ema_mid", "INTEGER NOT NULL DEFAULT 21")
        _add_column(conn, "ema_slow", "INTEGER NOT NULL DEFAULT 50")
        _add_column(conn, "sync_window", "INTEGER NOT NULL DEFAULT 3")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            pnl_pct REAL NOT NULL,
            peak_pnl_pct REAL NOT NULL,
            scanner_score REAL NOT NULL,
            micro_score REAL NOT NULL,
            bull_score REAL,
            bear_score REAL,
            action TEXT,
            reason TEXT,
            created_at REAL NOT NULL
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_history_symbol_time ON trade_history(symbol, created_at DESC)")

def save_trade(data: dict[str, Any]) -> None:
    init_db(); now = time.time()
    with connection() as conn:
        conn.execute("""
        INSERT INTO active_trade (
          id,symbol,side,entry_price,stop_loss_pct,take_profit_pct,
          trailing_activation_pct,trailing_drawdown_pct,refresh_seconds,
          status_update_minutes,telegram_enabled,sms_enabled,active,
          peak_pnl_pct,ema_fast,ema_mid,ema_slow,sync_window,created_at,updated_at
        ) VALUES (
          1,:symbol,:side,:entry_price,:stop_loss_pct,:take_profit_pct,
          :trailing_activation_pct,:trailing_drawdown_pct,:refresh_seconds,
          :status_update_minutes,:telegram_enabled,:sms_enabled,1,0,
          :ema_fast,:ema_mid,:ema_slow,:sync_window,:now,:now
        )
        ON CONFLICT(id) DO UPDATE SET
          symbol=excluded.symbol, side=excluded.side, entry_price=excluded.entry_price,
          stop_loss_pct=excluded.stop_loss_pct, take_profit_pct=excluded.take_profit_pct,
          trailing_activation_pct=excluded.trailing_activation_pct,
          trailing_drawdown_pct=excluded.trailing_drawdown_pct,
          refresh_seconds=excluded.refresh_seconds,
          status_update_minutes=excluded.status_update_minutes,
          telegram_enabled=excluded.telegram_enabled, sms_enabled=excluded.sms_enabled,
          ema_fast=excluded.ema_fast, ema_mid=excluded.ema_mid, ema_slow=excluded.ema_slow,
          sync_window=excluded.sync_window, active=1, peak_pnl_pct=0,
          last_action=NULL, last_alert_at=NULL, last_status_at=NULL,
          last_price=NULL, last_report_json=NULL, updated_at=excluded.updated_at
        """, {
            **data,
            "telegram_enabled": int(bool(data.get("telegram_enabled"))),
            "sms_enabled": int(bool(data.get("sms_enabled"))),
            "ema_fast": int(data.get("ema_fast", 9)),
            "ema_mid": int(data.get("ema_mid", 21)),
            "ema_slow": int(data.get("ema_slow", 50)),
            "sync_window": int(data.get("sync_window", 3)),
            "now": now,
        })

def get_trade() -> dict[str, Any] | None:
    init_db()
    with connection() as conn:
        row = conn.execute("SELECT * FROM active_trade WHERE id=1").fetchone()
    return dict(row) if row else None

def set_active(active: bool) -> None:
    init_db()
    with connection() as conn:
        conn.execute("UPDATE active_trade SET active=?, updated_at=? WHERE id=1", (int(active), time.time()))

def update_runtime(peak_pnl_pct: float, last_action: str, last_price: float,
                   report: dict[str, Any], alert_sent: bool=False, status_sent: bool=False) -> None:
    now = time.time()
    sets = ["peak_pnl_pct=?","last_action=?","last_price=?","last_report_json=?","updated_at=?"]
    vals: list[Any] = [peak_pnl_pct,last_action,last_price,json.dumps(report),now]
    if alert_sent:
        sets.append("last_alert_at=?"); vals.append(now)
    if status_sent:
        sets.append("last_status_at=?"); vals.append(now)
    vals.append(1)
    with connection() as conn:
        conn.execute(f"UPDATE active_trade SET {', '.join(sets)} WHERE id=?", vals)
        conn.execute("""
        INSERT INTO trade_history (
          symbol,side,price,pnl_pct,peak_pnl_pct,scanner_score,micro_score,
          bull_score,bear_score,action,reason,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            report.get("symbol", ""), report.get("side", ""), float(last_price),
            float(report.get("position_pnl_pct", 0)), float(peak_pnl_pct),
            float(report.get("scanner_score", 0)), float(report.get("micro_score", 0)),
            float(report.get("bull_score", 0)), float(report.get("bear_score", 0)),
            last_action, report.get("position_reason", ""), now,
        ))

def recent_trade_history(symbol: str, limit: int = 120) -> list[dict[str, Any]]:
    init_db()
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trade_history WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
            (symbol, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]

def clear_trade() -> None:
    init_db()
    with connection() as conn:
        conn.execute("DELETE FROM active_trade WHERE id=1")
