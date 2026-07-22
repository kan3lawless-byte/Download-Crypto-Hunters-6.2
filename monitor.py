from __future__ import annotations
import logging, os, threading, time
from typing import Any
from persistence import get_trade, init_db, update_runtime
from scanner import analyze_symbol, send_position_alert

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("crypto-hunters-monitor")

def pnl_pct(price: float, entry: float, side: str) -> float:
    sign = 1 if side == "LONG" else -1
    return (price / entry - 1) * 100 * sign

def decide(report: dict[str, Any], trade: dict[str, Any], pnl: float, peak: float):
    stop = float(trade["stop_loss_pct"])
    target = float(trade["take_profit_pct"])
    activation = float(trade["trailing_activation_pct"])
    trail = float(trade["trailing_drawdown_pct"])
    giveback = max(0.0, peak - pnl)

    if pnl <= -stop:
        return "EXIT — STOP LOSS", f"Move from entry is {pnl:+.2f}%, crossing the {stop:.2f}% stop."
    if pnl >= target:
        return "TAKE PROFIT", f"Move from entry reached {pnl:+.2f}%, meeting the {target:.2f}% target."
    if peak >= activation and giveback >= trail:
        return "TAKE PROFIT — TRAILING EXIT", (
            f"Best move was {peak:+.2f}%; current move is {pnl:+.2f}%, "
            f"a {giveback:.2f}% giveback."
        )
    if report["action"] in {"EXIT / DO NOT ENTER","AVOID"}:
        return "EXIT — REVERSAL WARNING", report["headline"]
    if peak >= activation and report["micro_score"] < 50:
        return "PROTECT PROFIT / TIGHTEN STOP", (
            f"Best move is {peak:+.2f}%, but 1M trigger weakened to {report['micro_score']:.0f}/100."
        )
    if pnl > 0:
        return "HOLD — PROFIT ACTIVE", f"Move from entry is {pnl:+.2f}%; no exit rule has fired."
    return "HOLD / MONITOR", f"Move from entry is {pnl:+.2f}%; position remains inside the risk plan."

def message(report, action, reason, pnl, peak):
    return (
        "CRYPTO HUNTERS POSITION UPDATE\n"
        f"{report['symbol']} {report['side']}\n"
        f"{action}\nPrice: {report['price']:.8g}\n"
        f"Move from entry: {pnl:+.2f}%\nBest move: {peak:+.2f}%\n"
        f"MTF score: {report['scanner_score']:.0f}/100\n"
        f"1M trigger: {report['micro_score']:.0f}/100\nReason: {reason}"
    )

def monitor_once() -> float:
    trade = get_trade()
    if not trade or not trade["active"]:
        return 15.0
    delay = max(10, int(trade["refresh_seconds"]))
    try:
        report = analyze_symbol(
            trade["symbol"], trade["side"], float(trade["entry_price"]),
            ema_fast=int(trade.get("ema_fast") or 9),
            ema_mid=int(trade.get("ema_mid") or 21),
            ema_slow=int(trade.get("ema_slow") or 50),
            sync_window=int(trade.get("sync_window") or 3),
        )
        current_pnl = pnl_pct(float(report["price"]), float(trade["entry_price"]), trade["side"])
        peak = max(float(trade.get("peak_pnl_pct") or 0), current_pnl)
        action, reason = decide(report, trade, current_pnl, peak)
        report.update({
            "position_action": action,
            "position_reason": reason,
            "position_pnl_pct": current_pnl,
            "peak_pnl_pct": peak,
            "drawdown_from_peak_pct": max(0.0, peak-current_pnl),
        })

        now = time.time()
        changed = action != (trade.get("last_action") or "")
        urgent = action.startswith(("EXIT","TAKE PROFIT","PROTECT PROFIT"))
        heartbeat_due = (
            int(trade["status_update_minutes"]) > 0 and
            now - float(trade.get("last_status_at") or 0) >= int(trade["status_update_minutes"]) * 60
        )
        alert_sent = status_sent = False

        if changed and urgent:
            send_position_alert(
                message(report, action, reason, current_pnl, peak),
                use_telegram=bool(trade["telegram_enabled"]),
                use_sms=bool(trade["sms_enabled"]),
            )
            alert_sent = True
        elif heartbeat_due:
            send_position_alert(
                message(report, "STATUS CHECK", reason, current_pnl, peak),
                use_telegram=bool(trade["telegram_enabled"]),
                use_sms=bool(trade["sms_enabled"]),
            )
            status_sent = True

        update_runtime(peak, action, float(report["price"]), report, alert_sent, status_sent)
    except Exception:
        log.exception("Monitor iteration failed")
    return float(delay)

def run_forever(stop_event: threading.Event | None=None):
    init_db()
    log.info("Background monitor started")
    while not (stop_event and stop_event.is_set()):
        delay = monitor_once()
        if stop_event:
            stop_event.wait(delay)
        else:
            time.sleep(delay)

if __name__ == "__main__":
    run_forever()
