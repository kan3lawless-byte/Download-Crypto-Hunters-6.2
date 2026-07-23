from __future__ import annotations

import json
import threading
import time

import pandas as pd
import streamlit as st

from monitor import monitor_once, run_forever
from persistence import clear_trade, get_trade, init_db, save_trade, set_active, recent_trade_history
from scanner import scan, validate_symbol
from tv_store import init_tv_tables, recent_signals
from market_intelligence import build_market_intelligence, normalize_symbol
from intelligence_store import init_intelligence_tables, recent_intelligence, save_intelligence

st.set_page_config(page_title="Crypto Hunters 5.3", page_icon="🥊", layout="wide")
st.markdown("""
<style>
.hunter-action-card {
  border: 1px solid rgba(128,128,128,.35);
  border-radius: .65rem;
  padding: .65rem .8rem;
  min-height: 5.2rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.hunter-action-label {font-size:.9rem; opacity:.78; margin-bottom:.25rem;}
.hunter-action-value {font-size:1.55rem; line-height:1.12; font-weight:600; overflow-wrap:anywhere;}
.hunter-live {color:#35d07f; font-weight:600;}
.hunter-error {color:#ff6b6b; font-weight:600;}
</style>
""", unsafe_allow_html=True)
init_db()
init_tv_tables()
init_intelligence_tables()


@st.cache_resource
def start_background_monitor():
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_forever,
        args=(stop_event,),
        daemon=True,
        name="crypto-hunters-background-monitor",
    )
    thread.start()
    return stop_event, thread


_monitor_stop, _monitor_thread = start_background_monitor()


@st.fragment(run_every="15s")
def render_live_trade_panel() -> None:
    saved = get_trade()
    if not saved:
        st.info("No saved trade is available.")
        return

    if bool(saved.get("active")):
        try:
            monitor_once()
        except Exception as exc:
            st.error(f"Live market check failed: {exc}")

    saved = get_trade()
    report = {}
    if saved and saved.get("last_report_json"):
        try:
            report = json.loads(saved["last_report_json"])
        except Exception:
            report = {}

    source = report.get("data_source", "Bitget USDT Perpetual") if report else "Bitget USDT Perpetual"
    connection = report.get("connection_status", "WAITING") if report else "WAITING"
    status_class = "hunter-live" if connection == "LIVE" else "hunter-error"
    st.markdown(
        f'<span class="{status_class}">● {connection}</span> — Market-data source: {source} • '
        f'Background monitor: {"Running" if _monitor_thread.is_alive() else "Stopped"}',
        unsafe_allow_html=True,
    )

    last_price = float((saved or {}).get("last_price") or 0)
    action_text = (saved or {}).get("last_action") or "WAITING"
    m1, m2, m3, m4 = st.columns([1, 1, 1, 1.25])
    m1.metric("Last price", f"{last_price:.8g}" if last_price else "Waiting...")
    m2.metric("Trade move", f"{float(report.get('position_pnl_pct', 0)):+.2f}%")
    m3.metric("Best move", f"{float((saved or {}).get('peak_pnl_pct') or 0):+.2f}%")
    with m4:
        st.markdown(
            f'<div class="hunter-action-card"><div class="hunter-action-label">Action</div>'
            f'<div class="hunter-action-value">{action_text}</div></div>',
            unsafe_allow_html=True,
        )

    if not report:
        st.warning(
            "No successful live report has been stored yet. Confirm that this exact contract exists "
            "on Bitget and wait for the next 15-second check."
        )
        return

    st.markdown("### Live Trade Commentary")
    action = report.get("position_action") or (saved or {}).get("last_action") or "MONITOR"
    reason = report.get("position_reason") or report.get("headline") or ""

    if str(action) in {"STOP EXIT", "TARGET HIT", "TRAILING EXIT", "REVERSAL EXIT"}:
        st.error(f"**{action}**")
    elif str(action).startswith("PROTECT"):
        st.warning(f"**{action}**")
    else:
        st.info(f"**{action}**")

    lines = [
        f"Current price is {float(report.get('price', 0)):.8g}.",
        f"Move from your entry is {float(report.get('position_pnl_pct', 0)):+.2f}%.",
        f"Best favorable move reached is {float(report.get('peak_pnl_pct', 0)):+.2f}%.",
        f"Multi-timeframe quality is {float(report.get('scanner_score', 0)):.0f}/100.",
        f"One-minute trigger strength is {float(report.get('micro_score', 0)):.0f}/100.",
        f"Reason: {reason}",
    ]
    for line in lines:
        st.write(f"• {line}")

    current_move = float(report.get("position_pnl_pct", 0))
    peak_move = float(report.get("peak_pnl_pct", 0))
    target_pct = float((saved or {}).get("take_profit_pct") or 0)
    activation_pct = float((saved or {}).get("trailing_activation_pct") or 0)
    giveback = float(report.get("drawdown_from_peak_pct", 0))
    st.markdown("#### Exit-rule status")
    r1, r2, r3 = st.columns(3)
    r1.write(f"**Target:** {'Reached' if current_move >= target_pct else 'Not reached'} ({target_pct:.2f}%)")
    r2.write(f"**Trailing:** {'Active' if peak_move >= activation_pct else 'Not active'} ({activation_pct:.2f}%)")
    r3.write(f"**Giveback from peak:** {giveback:.2f}%")

    raw_comments = report.get("commentary") or []
    if raw_comments:
        with st.expander("Indicator details", expanded=False):
            for line in raw_comments:
                st.write(f"• {line}")

    last_update = float((saved or {}).get("updated_at") or 0)
    if last_update:
        age = max(0, int(time.time() - last_update))
        st.caption(f"Last successful market check: approximately {age} seconds ago.")


st.title("🥊 Crypto Hunters 5.3")
st.caption("TradingView signals plus behind-the-chart market pressure intelligence")

scanner_tab, intelligence_tab, tv_tab, coach_tab = st.tabs(["🔎 Hunter Scanner", "🧠 Market Intelligence", "📡 TradingView Signals", "🎧 Persistent Trade Coach"])

with scanner_tab:
    c1, c2, c3, c4 = st.columns(4)
    minimum = c1.slider("Minimum score", 0, 100, 65)
    direction = c2.selectbox("Direction", ["Both", "LONG", "SHORT"])
    status = c3.selectbox("Status", ["All", "READY", "WAIT", "WATCH", "CAUTION", "SKIP"])
    run = c4.button("Run scan", type="primary", use_container_width=True)

    e1, e2, e3, e4 = st.columns(4)
    scan_ema_fast = e1.number_input("Fast EMA", min_value=2, max_value=100, value=9, step=1)
    scan_ema_mid = e2.number_input("Middle EMA", min_value=3, max_value=200, value=21, step=1)
    scan_ema_slow = e3.number_input("Slow EMA", min_value=5, max_value=400, value=50, step=1)
    scan_sync_window = e4.number_input("RSI/MACD window", min_value=0, max_value=10, value=3, step=1, help="How many candles RSI and MACD may take to align.")

    if "results" not in st.session_state:
        st.session_state.results = pd.DataFrame()

    if run:
        with st.spinner("Scanning Bitget USDT perpetuals..."):
            try:
                st.session_state.results = scan(int(scan_ema_fast), int(scan_ema_mid), int(scan_ema_slow), int(scan_sync_window))
            except Exception as exc:
                st.exception(exc)

    frame = st.session_state.results
    if frame.empty:
        st.info("Run the scanner to begin.")
    else:
        filtered = frame[frame["score"] >= minimum].copy()
        if direction != "Both":
            filtered = filtered[filtered["side"] == direction]
        if status != "All":
            filtered = filtered[filtered["status"].str.startswith(status)]

        visible = [
            "symbol", "side", "grade", "score", "status", "price",
            "trend_4h", "confirm_1h", "setup_15m", "entry_5m",
            "extension_5m_pct", "ema_alignment", "rsi_macd_sync", "warnings",
        ]
        st.dataframe(filtered[visible], use_container_width=True, hide_index=True)

        if not filtered.empty:
            choices = [f"{row.symbol} • {row.side} • {row.score:.0f}/100" for row in filtered.itertuples()]
            selected_setup = st.selectbox("Choose a scanner result to send to the Trade Coach", choices)
            if st.button("Send selected setup to Trade Coach", use_container_width=True):
                selected_index = choices.index(selected_setup)
                picked = filtered.iloc[selected_index]
                st.session_state.coach_prefill = {
                    "symbol": picked["symbol"],
                    "side": picked["side"],
                    "ema_fast": int(scan_ema_fast),
                    "ema_mid": int(scan_ema_mid),
                    "ema_slow": int(scan_ema_slow),
                    "sync_window": int(scan_sync_window),
                }
                st.success(f"{picked['symbol']} {picked['side']} is ready in the Trade Coach tab. Enter your actual entry price and start monitoring.")

with intelligence_tab:
    st.subheader("Behind-the-Chart Market Intelligence")
    st.caption("Reads visible liquidity, funding, spread, volume impulse, short-term directional pressure, and futures basis from Bitunix public market data.")
    a, b = st.columns([3, 1])
    intelligence_symbol = a.text_input("Bitunix perpetual contract", value="BTCUSDT", key="intelligence_symbol").upper().replace("/", "")
    refresh_intelligence = b.button("Analyze now", type="primary", use_container_width=True)

    if refresh_intelligence:
        with st.spinner("Reading the order book and futures market internals..."):
            try:
                report = build_market_intelligence(intelligence_symbol)
                save_intelligence(report)
                st.session_state.market_intelligence_report = report
            except Exception as exc:
                st.error(f"Market-intelligence check failed: {exc}")

    report = st.session_state.get("market_intelligence_report")
    if report and normalize_symbol(report.get("symbol", "")) == normalize_symbol(intelligence_symbol):
        st.markdown(f"### {report['symbol']} — {report['regime']}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Pressure direction", report["direction"])
        m2.metric("Long pressure", f"{report['long_pressure_score']:.1f}/100")
        m3.metric("Short pressure", f"{report['short_pressure_score']:.1f}/100")
        m4.metric("Directional edge", f"{report['pressure_edge']:.1f} points")

        st.markdown("#### What is happening behind the candles")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Order-book imbalance", f"{report['book_imbalance_pct']:+.1f}%", help="Positive means more visible bid notional; negative means more visible ask notional in the sampled levels.")
        c2.metric("Recent buy pressure", f"{report['buy_pressure_pct']:+.1f}%", help="Directional quote-volume proxy from recent one-minute candles; not true exchange-wide buyer identity.")
        c3.metric("Volume impulse", f"{report['volume_impulse']:.2f}×")
        c4.metric("Range expansion", f"{report['range_expansion']:.2f}×")

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Funding rate", f"{report['funding_rate_pct']:+.5f}%")
        d2.metric("Funding crowding", f"{report['funding_crowding']:.0f}/100")
        d3.metric("Spread", f"{report['spread_bps']:.2f} bps")
        d4.metric("Mark/index basis", f"{report['basis_bps']:+.2f} bps")

        explanation = []
        if report['book_imbalance_pct'] > 10:
            explanation.append("Visible bids outweigh asks in the sampled order-book levels.")
        elif report['book_imbalance_pct'] < -10:
            explanation.append("Visible asks outweigh bids in the sampled order-book levels.")
        else:
            explanation.append("The visible order book is relatively balanced.")
        if report['volume_impulse'] >= 1.5:
            explanation.append("Participation is accelerating compared with the recent local baseline.")
        elif report['volume_impulse'] < 1.0:
            explanation.append("Participation is weaker than the recent local baseline.")
        if abs(report['buy_pressure_pct']) >= 15:
            side = "buying" if report['buy_pressure_pct'] > 0 else "selling"
            explanation.append(f"Recent candle-volume pressure favors {side}.")
        if report['funding_crowding'] >= 70:
            explanation.append("Futures positioning appears crowded, which raises squeeze and liquidation risk.")
        for line in explanation:
            st.write(f"• {line}")

        if report.get("warnings"):
            st.warning("\n".join(f"• {item}" for item in report["warnings"]))

        history = list(reversed(recent_intelligence(report['symbol'], 50)))
        if len(history) >= 2:
            history_frame = pd.DataFrame(history)
            history_frame['time'] = pd.to_datetime(history_frame['created_at'], unit='s')
            st.markdown("#### Pressure history")
            st.line_chart(history_frame.set_index('time')[["long_pressure_score", "short_pressure_score"]])

        with st.expander("Important limitations", expanded=True):
            for item in report.get("limitations", []):
                st.write(f"• {item}")
    else:
        st.info("Enter a Bitunix USDT perpetual symbol and select Analyze now.")


with tv_tab:
    st.subheader("TradingView Signal Inbox")
    st.caption("Signals arrive here from the Hunter Pine Script through the TradingView webhook.")
    signals = recent_signals(200)
    if not signals:
        st.info("No TradingView webhook signals have been received yet.")
    else:
        tv_frame = pd.DataFrame(signals)
        tv_frame["received"] = pd.to_datetime(tv_frame["received_at"], unit="s")
        visible = ["received", "exchange", "symbol", "timeframe", "direction", "signal", "score", "price", "atr_pct", "rvol", "extension_pct"]
        st.dataframe(tv_frame[visible], use_container_width=True, hide_index=True)
        latest = tv_frame.iloc[0]
        st.markdown("### Latest signal")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Contract", f"{latest.get('exchange','')}:{latest.get('symbol','')}")
        c2.metric("Direction", str(latest.get("direction", "")))
        c3.metric("Hunter score", f"{float(latest.get('score',0)):.0f}/100")
        c4.metric("Signal", str(latest.get("signal", "")))
        st.caption("TradingView supplies the signal. Direct exchange feeds still handle continuous price monitoring, funding, spread, and order-book checks.")

with coach_tab:
    saved = get_trade()
    defaults = saved or {
        "symbol": "XRPUSDT",
        "side": "LONG",
        "entry_price": 0.0,
        "stop_loss_pct": 1.0,
        "take_profit_pct": 2.0,
        "trailing_activation_pct": 1.0,
        "trailing_drawdown_pct": 0.5,
        "refresh_seconds": 15,
        "status_update_minutes": 10,
        "telegram_enabled": 0,
        "sms_enabled": 0,
        "active": 0,
        "ema_fast": 9,
        "ema_mid": 21,
        "ema_slow": 50,
        "sync_window": 3,
    }

    prefill = st.session_state.get("coach_prefill", {})
    if not saved and prefill:
        defaults.update(prefill)

    if saved:
        state = "ACTIVE" if saved["active"] else "PAUSED"
        st.success(f"Remembered trade: **{saved['symbol']} {saved['side']}** — {state}")
    else:
        st.info("No trade is saved yet.")

    with st.form("trade_form"):
        a, b, c = st.columns(3)
        symbol = a.text_input("Contract", value=str(defaults["symbol"]), help="You may enter DEXEUSDT, DEXE/USDT, DEXE-USDT, or DEXE_USDT.")
        side = b.selectbox(
            "Direction",
            ["LONG", "SHORT"],
            index=0 if defaults["side"] == "LONG" else 1,
        )
        entry = c.number_input(
            "Entry price",
            min_value=0.0,
            value=float(defaults["entry_price"]),
            format="%.8f",
        )

        d, e, f, g = st.columns(4)
        stop = d.number_input(
            "Stop-loss %",
            min_value=0.05,
            value=float(defaults["stop_loss_pct"]),
            step=0.1,
        )
        target = e.number_input(
            "Take-profit %",
            min_value=0.05,
            value=float(defaults["take_profit_pct"]),
            step=0.1,
        )
        activation = f.number_input(
            "Trail activates at %",
            min_value=0.05,
            value=float(defaults["trailing_activation_pct"]),
            step=0.1,
        )
        trail = g.number_input(
            "Allowed giveback %",
            min_value=0.05,
            value=float(defaults["trailing_drawdown_pct"]),
            step=0.1,
        )

        ema1, ema2, ema3, ema4 = st.columns(4)
        coach_ema_fast = ema1.number_input("Fast EMA", min_value=2, max_value=100, value=int(defaults.get("ema_fast", 9)), step=1, key="coach_ema_fast")
        coach_ema_mid = ema2.number_input("Middle EMA", min_value=3, max_value=200, value=int(defaults.get("ema_mid", 21)), step=1, key="coach_ema_mid")
        coach_ema_slow = ema3.number_input("Slow EMA", min_value=5, max_value=400, value=int(defaults.get("ema_slow", 50)), step=1, key="coach_ema_slow")
        coach_sync_window = ema4.number_input("RSI/MACD window", min_value=0, max_value=10, value=int(defaults.get("sync_window", 3)), step=1, key="coach_sync_window")

        h, i, j, k = st.columns(4)
        refresh_options = [10, 15, 30, 60]
        saved_refresh = int(defaults.get("refresh_seconds", 15))
        refresh = h.selectbox("Market check", refresh_options, index=refresh_options.index(saved_refresh) if saved_refresh in refresh_options else 1)
        heartbeat = i.selectbox(
            "Status messages",
            [0, 5, 10, 15, 30, 60],
            index=2,
            format_func=lambda x: "Urgent only" if x == 0 else f"Every {x} min",
        )
        telegram = j.checkbox("Telegram", value=bool(defaults["telegram_enabled"]))
        sms = k.checkbox("SMS text", value=bool(defaults["sms_enabled"]))

        save = st.form_submit_button(
            "Update trade settings" if saved else "Save and start monitoring",
            type="primary",
            use_container_width=True,
        )

    if save:
        if entry <= 0:
            st.error("Enter your actual trade-entry price.")
        else:
            try:
                symbol_check = validate_symbol(symbol)
                normalized_symbol = symbol_check["symbol"]
                live_price = float(symbol_check["price"])
                entry_gap_pct = abs(entry / live_price - 1) * 100
                if entry_gap_pct > 25:
                    st.error(
                        f"Entry price {entry:.8g} is {entry_gap_pct:.2f}% away from the live "
                        f"{normalized_symbol} price of {live_price:.8g}. Check the KCEX contract and entry price before monitoring."
                    )
                    st.stop()
            except Exception as exc:
                st.error(
                    f"No live Bitget data was found for this contract: {exc}. "
                    "The coin may exist on KCEX but not on Bitget, which is Crypto Hunters' current market-data source."
                )
                st.stop()

            save_trade(
                {
                    "symbol": normalized_symbol,
                    "side": side,
                    "entry_price": entry,
                    "stop_loss_pct": stop,
                    "take_profit_pct": target,
                    "trailing_activation_pct": activation,
                    "trailing_drawdown_pct": trail,
                    "refresh_seconds": refresh,
                    "status_update_minutes": heartbeat,
                    "telegram_enabled": telegram,
                    "sms_enabled": sms,
                    "ema_fast": int(coach_ema_fast),
                    "ema_mid": int(coach_ema_mid),
                    "ema_slow": int(coach_ema_slow),
                    "sync_window": int(coach_sync_window),
                }
            )
            try:
                monitor_once()
            except Exception as exc:
                st.warning(f"Trade was saved, but the first live check failed: {exc}")
            st.success(f"{normalized_symbol} matched successfully. Live Bitget monitoring is active.")
            st.rerun()

    if saved:
        x, y, z = st.columns(3)
        if x.button("Pause monitoring", use_container_width=True):
            set_active(False)
            st.rerun()
        if y.button("Resume monitoring", use_container_width=True):
            set_active(True)
            st.rerun()
        if z.button("Clear saved trade", use_container_width=True):
            clear_trade()
            st.rerun()

        if st.button("Refresh now", use_container_width=True):
            try:
                monitor_once()
            except Exception as exc:
                st.error(f"Manual refresh failed: {exc}")
            st.rerun()

        render_live_trade_panel()

        history = list(reversed(recent_trade_history(saved["symbol"], 120)))
        if history:
            st.markdown("### 15-second Hunter trail")
            history_frame = pd.DataFrame(history)
            history_frame["time"] = pd.to_datetime(history_frame["created_at"], unit="s")
            st.line_chart(history_frame.set_index("time")[["scanner_score", "micro_score", "bull_score", "bear_score"]])
            trail_visible = ["time", "price", "pnl_pct", "scanner_score", "micro_score", "action", "reason"]
            st.dataframe(history_frame[trail_visible].tail(30).sort_values("time", ascending=False), use_container_width=True, hide_index=True)

    st.warning(
        "Crypto Hunters can monitor only contracts available from its current Bitget USDT-perpetual data source. "
        "A KCEX-listed coin that is unavailable on Bitget will be rejected with a clear message. "
        "Off-page Telegram or SMS monitoring still depends on the server remaining awake."
    )
