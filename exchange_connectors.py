from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass
class ConnectionResult:
    venue: str
    configured: bool
    live_trading_ready: bool
    message: str


def connection_status(venue: str) -> ConnectionResult:
    venue = venue.upper()
    if venue == 'COINBASE ADVANCED':
        configured = bool(os.getenv('COINBASE_API_KEY') and os.getenv('COINBASE_API_SECRET'))
        return ConnectionResult(
            venue=venue,
            configured=configured,
            live_trading_ready=False,
            message=(
                'Credentials detected. Live order transmission remains intentionally locked in 6.0 until paper results and a separate enable-live review are completed.'
                if configured else
                'Add a trade-only Coinbase Advanced API key through server secrets. Never paste credentials into the app or chat.'
            ),
        )
    if venue == 'KRAKEN SPOT':
        configured = bool(os.getenv('KRAKEN_API_KEY') and os.getenv('KRAKEN_API_SECRET'))
        return ConnectionResult(
            venue=venue,
            configured=configured,
            live_trading_ready=False,
            message=(
                'Credentials detected. Live order transmission remains intentionally locked in 6.0 until paper validation is complete.'
                if configured else
                'Add a Kraken trade-only API key through server secrets, with withdrawal permission disabled.'
            ),
        )
    return ConnectionResult(venue=venue, configured=False, live_trading_ready=False, message='Unsupported venue.')
