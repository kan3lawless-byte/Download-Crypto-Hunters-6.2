from __future__ import annotations

import math
import time
from typing import Any

import requests

BASE_URL = "https://fapi.bitunix.com/api/v1/futures/market"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CryptoHunters/5.1"})


def _get(path: str, params: dict[str, Any]) -> Any:
    response = SESSION.get(f"{BASE_URL}/{path}", params=params, timeout=8)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg") or f"Bitunix API error: {payload.get('code')}")
    return payload.get("data")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").upper().replace("/", "").replace("-", "")
    if ":" in value:
        value = value.split(":", 1)[1]
    if value.endswith(".P"):
        value = value[:-2]
    return value


def fetch_depth(symbol: str, limit: str = "50") -> dict[str, Any]:
    return _get("depth", {"symbol": normalize_symbol(symbol), "limit": limit})


def fetch_funding(symbol: str) -> dict[str, Any]:
    return _get("funding_rate", {"symbol": normalize_symbol(symbol)})


def fetch_ticker(symbol: str) -> dict[str, Any]:
    rows = _get("tickers", {"symbols": normalize_symbol(symbol)}) or []
    if not rows:
        raise RuntimeError("Bitunix returned no ticker for this symbol")
    return rows[0]


def fetch_klines(symbol: str, interval: str = "1m", limit: int = 60) -> list[dict[str, Any]]:
    rows = _get("kline", {
        "symbol": normalize_symbol(symbol),
        "interval": interval,
        "limit": max(10, min(200, int(limit))),
        "type": "LAST_PRICE",
    }) or []
    return sorted(rows, key=lambda row: int(row.get("time", 0)))


def analyze_order_book(depth: dict[str, Any], levels: int = 15) -> dict[str, float]:
    asks = depth.get("asks") or []
    bids = depth.get("bids") or []
    asks = asks[:levels]
    bids = bids[:levels]
    ask_notional = sum(_f(p) * _f(q) for p, q in asks)
    bid_notional = sum(_f(p) * _f(q) for p, q in bids)
    total = bid_notional + ask_notional
    imbalance = (bid_notional - ask_notional) / total if total else 0.0
    best_ask = _f(asks[0][0]) if asks else 0.0
    best_bid = _f(bids[0][0]) if bids else 0.0
    midpoint = (best_ask + best_bid) / 2 if best_ask and best_bid else 0.0
    spread_bps = ((best_ask - best_bid) / midpoint * 10000) if midpoint else 0.0
    return {
        "bid_notional": bid_notional,
        "ask_notional": ask_notional,
        "book_imbalance": imbalance,
        "spread_bps": spread_bps,
    }


def analyze_klines(rows: list[dict[str, Any]]) -> dict[str, float]:
    if len(rows) < 10:
        return {
            "volume_impulse": 0.0,
            "buy_pressure": 0.0,
            "price_change_pct": 0.0,
            "range_expansion": 0.0,
        }

    closes = [_f(r.get("close")) for r in rows]
    opens = [_f(r.get("open")) for r in rows]
    highs = [_f(r.get("high")) for r in rows]
    lows = [_f(r.get("low")) for r in rows]
    vols = [_f(r.get("quoteVol")) for r in rows]

    recent_n = min(5, len(rows) // 3)
    base = vols[:-recent_n] or vols
    avg_base = sum(base) / len(base) if base else 0.0
    avg_recent = sum(vols[-recent_n:]) / recent_n if recent_n else 0.0
    volume_impulse = avg_recent / avg_base if avg_base else 0.0

    directional_volume = 0.0
    total_volume = 0.0
    for o, c, v in zip(opens[-12:], closes[-12:], vols[-12:]):
        total_volume += v
        directional_volume += v if c > o else -v if c < o else 0.0
    buy_pressure = directional_volume / total_volume if total_volume else 0.0

    start = closes[-recent_n - 1] if len(closes) > recent_n else closes[0]
    end = closes[-1]
    price_change_pct = ((end / start) - 1) * 100 if start else 0.0

    ranges = [(h - l) for h, l in zip(highs, lows)]
    old_ranges = ranges[:-recent_n] or ranges
    recent_range = sum(ranges[-recent_n:]) / recent_n
    old_range = sum(old_ranges) / len(old_ranges) if old_ranges else 0.0
    range_expansion = recent_range / old_range if old_range else 0.0

    return {
        "volume_impulse": volume_impulse,
        "buy_pressure": buy_pressure,
        "price_change_pct": price_change_pct,
        "range_expansion": range_expansion,
    }


def build_market_intelligence(symbol: str) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    depth = fetch_depth(symbol)
    funding = fetch_funding(symbol)
    ticker = fetch_ticker(symbol)
    klines = fetch_klines(symbol, "1m", 60)

    book = analyze_order_book(depth)
    tape = analyze_klines(klines)

    funding_rate = _f(funding.get("fundingRate"))
    mark = _f(funding.get("markPrice") or ticker.get("markPrice"))
    index = _f(funding.get("indexPrice"))
    basis_bps = ((mark - index) / index * 10000) if index else 0.0

    # Independent evidence components. These are quality/pressure scores, not win probabilities.
    book_long = _clamp(50 + book["book_imbalance"] * 50)
    tape_long = _clamp(50 + tape["buy_pressure"] * 50)
    momentum_long = _clamp(50 + tape["price_change_pct"] * 12)
    volume_quality = _clamp((tape["volume_impulse"] - 0.5) * 50)
    range_quality = _clamp((tape["range_expansion"] - 0.5) * 50)

    # Positive funding means longs pay shorts: modest positive can confirm demand, extreme positive is crowding.
    funding_pct = funding_rate * 100
    crowding = _clamp(abs(funding_pct) / 0.05 * 100)
    if abs(funding_pct) < 0.01:
        funding_long = 50.0
    elif funding_pct > 0:
        funding_long = _clamp(58 - crowding * 0.18)
    else:
        funding_long = _clamp(42 + crowding * 0.18)

    liquidity_quality = _clamp(100 - book["spread_bps"] * 8)
    basis_long = _clamp(50 + basis_bps * 2)

    long_score = (
        book_long * 0.24
        + tape_long * 0.20
        + momentum_long * 0.16
        + volume_quality * 0.14
        + range_quality * 0.08
        + funding_long * 0.08
        + liquidity_quality * 0.06
        + basis_long * 0.04
    )
    short_score = (
        (100 - book_long) * 0.24
        + (100 - tape_long) * 0.20
        + (100 - momentum_long) * 0.16
        + volume_quality * 0.14
        + range_quality * 0.08
        + (100 - funding_long) * 0.08
        + liquidity_quality * 0.06
        + (100 - basis_long) * 0.04
    )

    direction = "LONG" if long_score >= short_score else "SHORT"
    edge = abs(long_score - short_score)
    if max(long_score, short_score) >= 72 and edge >= 12:
        regime = "STRONG PRESSURE"
    elif max(long_score, short_score) >= 60 and edge >= 6:
        regime = "BUILDING"
    else:
        regime = "MIXED / WAIT"

    warnings: list[str] = []
    if book["spread_bps"] > 8:
        warnings.append("Wide spread: execution and slippage risk are elevated.")
    if crowding > 70:
        warnings.append("Funding is crowded; liquidation or squeeze risk is elevated.")
    if tape["volume_impulse"] < 1.0:
        warnings.append("Recent volume is below its local baseline.")
    if tape["range_expansion"] > 2.0:
        warnings.append("Range is expanding quickly; avoid chasing after the move is extended.")

    return {
        "symbol": symbol,
        "timestamp": time.time(),
        "direction": direction,
        "regime": regime,
        "long_pressure_score": round(long_score, 1),
        "short_pressure_score": round(short_score, 1),
        "pressure_edge": round(edge, 1),
        "last_price": _f(ticker.get("lastPrice") or ticker.get("last")),
        "mark_price": mark,
        "index_price": index,
        "basis_bps": round(basis_bps, 2),
        "funding_rate_pct": round(funding_pct, 5),
        "funding_crowding": round(crowding, 1),
        "book_imbalance_pct": round(book["book_imbalance"] * 100, 1),
        "bid_notional": round(book["bid_notional"], 2),
        "ask_notional": round(book["ask_notional"], 2),
        "spread_bps": round(book["spread_bps"], 2),
        "volume_impulse": round(tape["volume_impulse"], 2),
        "buy_pressure_pct": round(tape["buy_pressure"] * 100, 1),
        "price_change_5m_pct": round(tape["price_change_pct"], 3),
        "range_expansion": round(tape["range_expansion"], 2),
        "liquidity_quality": round(liquidity_quality, 1),
        "warnings": warnings,
        "limitations": [
            "Visible order-book liquidity can be moved or canceled and is not guaranteed to execute.",
            "This public Bitunix feed does not provide a market-wide spot-flow or institutional-flow total.",
            "Open-interest confirmation is not included because the current public market endpoints used here do not expose it.",
            "Scores measure evidence alignment and pressure; they are not probabilities or guarantees.",
        ],
    }
