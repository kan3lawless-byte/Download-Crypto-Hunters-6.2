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
from automation_engine import RiskPolicy, position_plan, load_state, save_state, log_event
from exchange_connectors import connection_status

st.set_page_config(page_title="Crypto Hunters 6.1", page_icon="🥊", layout="wide")
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


st.title("🥊 Crypto Hunters 6.1")
st.caption("TradingView signals plus behind-the-chart market pressure intelligence")

scanner_tab, predictor_tab, intelligence_tab, tv_tab, coach_tab, auto_tab = st.tabs(["🔎 Hunter Scanner", "🔮 Profit Predictor", "🧠 Market Intelligence", "📡 TradingView Signals", "🎧 Persistent Trade Coach", "🤖 Safe Automation"])

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

with predictor_tab:
    st.subheader("Profit Predictor — best setup or no trade")
    st.caption("Ranks continuation setups using 4H/1H/15M/5M alignment, RSI/MACD agreement, extension risk, liquidity, and recent volatility. It estimates probability-like confidence; it cannot guarantee a green result.")

    p1, p2, p3, p4 = st.columns(4)
    pred_min_conf = p1.slider("Minimum confidence", 60, 95, 80)
    pred_min_score = p2.slider("Minimum Hunter score", 60, 100, 82)
    pred_direction = p3.selectbox("Prediction direction", ["Both", "LONG", "SHORT"], key="predictor_direction")
    pred_run = p4.button("Find best setup", type="primary", use_container_width=True)

    st.markdown("##### Profit-protection filters")
    q1, q2, q3 = st.columns(3)
    max_extension = q1.number_input("Maximum 5M extension %", min_value=0.5, max_value=10.0, value=2.5, step=0.1)
    require_sync = q2.toggle("Require RSI/MACD agreement", value=True)
    require_ready = q3.toggle("Require READY status", value=True)

    if pred_run:
        with st.spinner("Searching for the strongest continuation setup..."):
            try:
                st.session_state.predictor_results = scan(9, 21, 50, 3)
            except Exception as exc:
                st.error(f"Prediction scan failed: {exc}")

    pred_frame = st.session_state.get("predictor_results", pd.DataFrame())
    if pred_frame.empty:
        st.info("Select **Find best setup**. Hunter will either identify one qualified setup or tell you not to trade.")
    else:
        candidates = pred_frame.copy()
        candidates = candidates[candidates["score"] >= pred_min_score]
        candidates = candidates[candidates["continuation_confidence"] >= pred_min_conf]
        candidates = candidates[candidates["extension_5m_pct"] <= float(max_extension)]
        if pred_direction != "Both":
            candidates = candidates[candidates["side"] == pred_direction]
        if require_sync:
            candidates = candidates[candidates["rsi_macd_sync"] == True]
        if require_ready:
            candidates = candidates[candidates["status"].str.startswith("READY")]
        candidates = candidates.sort_values(["continuation_confidence", "score", "volume24h_usdt"], ascending=[False, False, False])

        if candidates.empty:
            st.error("NO TRADE — no market currently passes all profit-protection filters. Waiting is a valid trading decision.")
        else:
            best = candidates.iloc[0]
            side_icon = "🟢" if best["side"] == "LONG" else "🔴"
            st.success(f"{side_icon} BEST CURRENT SETUP: {best['symbol']} {best['side']}")
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Continuation confidence", f"{best['continuation_confidence']:.0f}/100")
            a2.metric("Hunter score", f"{best['score']:.0f}/100")
            a3.metric("Estimated move zone", f"{best['projected_move_low_pct']:.2f}%–{best['projected_move_high_pct']:.2f}%")
            a4.metric("5M extension", f"{best['extension_5m_pct']:.2f}%")

            st.markdown("##### Clear decision")
            if best["prediction"] == "HIGH-CONVICTION":
                st.info("**ENTER ONLY AFTER YOUR CHART CONFIRMS THE CLOSED CANDLE.** Use a predefined stop and take partial profit rather than waiting for an unlimited move.")
            else:
                st.warning("**WATCH / WAIT FOR CONFIRMATION.** The setup is favorable but not strong enough to treat as a high-conviction entry.")

            st.write(f"• Direction: **{best['side']}**")
            st.write(f"• EMA alignment: **{best['ema_alignment']}**")
            st.write(f"• RSI/MACD agreement: **{'Yes' if best['rsi_macd_sync'] else 'No'}**")
            st.write(f"• 4H + 1H quality: **{best['trend_4h'] + best['confirm_1h']:.0f}/50**")
            st.write(f"• 15M + 5M entry quality: **{best['setup_15m'] + best['entry_5m']:.0f}/50**")
            if best.get("warnings"):
                st.warning(f"Warning: {best['warnings']}")

            st.markdown("##### Other qualified setups")
            show_cols = ["symbol", "side", "prediction", "continuation_confidence", "score", "projected_move_low_pct", "projected_move_high_pct", "extension_5m_pct", "status"]
            st.dataframe(candidates.head(10)[show_cols], use_container_width=True, hide_index=True)

            st.caption("Estimated move zones are ATR-based ranges, not promises. Fees, slippage, reversals, and news can turn any setup red.")

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


with auto_tab:
    st.subheader("Safe Automation — paper first, live later")
    st.caption("This module separates Hunter decisions, risk approval, and exchange execution. Version 6.1 cannot transmit live orders; it is deliberately paper-only until the strategy proves an edge.")

    state = load_state()
    saved_policy = state.get("policy", {})
    venue = st.selectbox("Planned execution venue", ["Coinbase Advanced", "Kraken Spot"], help="Coinbase is the first-choice U.S. venue for this build. Kraken Spot is the backup.")
    status = connection_status(venue)
    if status.configured:
        st.success(f"API configuration detected for {status.venue}. {status.message}")
    else:
        st.info(status.message)

    c1, c2, c3, c4 = st.columns(4)
    capital = c1.number_input("Trading capital", min_value=1.0, value=float(saved_policy.get("starting_capital", 15.0)), step=1.0)
    risk_pct = c2.number_input("Risk per trade %", min_value=0.1, max_value=5.0, value=float(saved_policy.get("risk_per_trade_pct", 1.0)), step=0.1)
    max_position_pct = c3.number_input("Maximum position %", min_value=1.0, max_value=100.0, value=float(saved_policy.get("max_position_pct", 20.0)), step=1.0)
    daily_loss_pct = c4.number_input("Daily loss limit %", min_value=0.5, max_value=10.0, value=float(saved_policy.get("max_daily_loss_pct", 3.0)), step=0.5)

    d1, d2, d3, d4 = st.columns(4)
    max_trades = d1.number_input("Maximum trades/day", min_value=1, max_value=20, value=int(saved_policy.get("max_trades_per_day", 3)), step=1)
    min_score = d2.number_input("Minimum Hunter score", min_value=60, max_value=100, value=int(saved_policy.get("min_hunter_score", 78)), step=1)
    d3.metric("Leverage", "1×", help="Growth mode is intentionally spot-only and unleveraged in version 6.1.")
    kill_switch = d4.toggle("Kill switch", value=bool(state.get("kill_switch", True)), help="ON blocks every future order path.")

    policy = RiskPolicy(
        mode="PAPER", starting_capital=float(capital), risk_per_trade_pct=float(risk_pct),
        max_position_pct=float(max_position_pct), max_daily_loss_pct=float(daily_loss_pct),
        max_trades_per_day=int(max_trades), min_hunter_score=int(min_score), leverage=1.0,
    )
    errors = policy.validate()
    if errors:
        st.error("\n".join(errors))
    if st.button("Save automation safety rules", type="primary", use_container_width=True, disabled=bool(errors)):
        state["policy"] = policy.__dict__
        state["kill_switch"] = bool(kill_switch)
        state["venue"] = venue
        save_state(state)
        log_event("SETTINGS", "Automation safety rules updated.", policy.__dict__)
        st.success("Safety rules saved. Paper mode remains active and live execution remains locked.")

    st.markdown("### Position-size preview")
    p1, p2 = st.columns(2)
    preview_entry = p1.number_input("Example entry price", min_value=0.00000001, value=1.0, format="%.8f")
    preview_stop = p2.number_input("Example stop distance %", min_value=0.1, max_value=20.0, value=1.0, step=0.1)
    plan = position_plan(policy, float(preview_entry), float(preview_stop))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Dollars at risk", f"${plan['risk_dollars']:.2f}")
    m2.metric("Maximum notional", f"${plan['notional']:.2f}")
    m3.metric("Estimated quantity", f"{plan['quantity']:.8g}")
    m4.metric("Daily stop", f"${plan['daily_loss_limit_dollars']:.2f}")

    st.markdown("### Mandatory path before live automation")
    st.write("1. Run paper automation and collect at least 100 completed trades.")
    st.write("2. Require positive results after fees and slippage, with an acceptable maximum drawdown.")
    st.write("3. Start live with spot only, one position at a time, no leverage, and withdrawal-disabled API permissions.")
    st.write("4. Keep the kill switch on until a separate live-enablement review is completed.")

    with st.expander("API security requirements", expanded=True):
        st.write("• Never enter an exchange password, 2FA code, seed phrase, or API secret into chat.")
        st.write("• Store keys only in deployment secrets or environment variables.")
        st.write("• Enable balance/order permissions only; disable withdrawals.")
        st.write("• Restrict the API key to the server IP when the exchange supports it.")
        st.write("• Use a dedicated sub-portfolio or small balance for the first live test.")
