from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import time

STATE_FILE = Path('automation_state.json')


@dataclass
class RiskPolicy:
    mode: str = 'PAPER'
    starting_capital: float = 15.0
    risk_per_trade_pct: float = 1.0
    max_position_pct: float = 20.0
    max_daily_loss_pct: float = 3.0
    max_trades_per_day: int = 3
    min_hunter_score: int = 78
    require_closed_candle: bool = True
    one_position_only: bool = True
    leverage: float = 1.0

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.starting_capital <= 0:
            errors.append('Capital must be greater than zero.')
        if not 0.1 <= self.risk_per_trade_pct <= 5:
            errors.append('Risk per trade must be between 0.1% and 5%.')
        if not 1 <= self.max_position_pct <= 100:
            errors.append('Maximum position size must be between 1% and 100%.')
        if not 0.5 <= self.max_daily_loss_pct <= 10:
            errors.append('Daily loss limit must be between 0.5% and 10%.')
        if not 1 <= self.max_trades_per_day <= 20:
            errors.append('Maximum trades per day must be between 1 and 20.')
        if self.leverage != 1.0 and self.mode == 'PAPER':
            errors.append('Version 6.0 paper-growth mode is intentionally locked to 1× leverage.')
        return errors


def position_plan(policy: RiskPolicy, entry: float, stop_pct: float) -> dict:
    risk_dollars = policy.starting_capital * policy.risk_per_trade_pct / 100
    stop_fraction = max(stop_pct / 100, 0.0001)
    risk_based_notional = risk_dollars / stop_fraction
    position_cap = policy.starting_capital * policy.max_position_pct / 100
    notional = min(risk_based_notional, position_cap)
    quantity = notional / entry if entry > 0 else 0
    return {
        'risk_dollars': risk_dollars,
        'notional': notional,
        'quantity': quantity,
        'daily_loss_limit_dollars': policy.starting_capital * policy.max_daily_loss_pct / 100,
    }


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {'kill_switch': True, 'policy': asdict(RiskPolicy()), 'events': []}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {'kill_switch': True, 'policy': asdict(RiskPolicy()), 'events': []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(kind: str, message: str, payload: dict | None = None) -> None:
    state = load_state()
    state.setdefault('events', []).append({
        'created_at': time.time(),
        'kind': kind,
        'message': message,
        'payload': payload or {},
    })
    state['events'] = state['events'][-250:]
    save_state(state)
