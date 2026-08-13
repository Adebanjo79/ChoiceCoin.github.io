"""Live runtime status shared between scanner and Telegram commands."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RuntimeStatus:
    phase: str = "starting"  # starting | scanning | waiting | error
    cycle: int = 0
    mode: str = ""
    min_confidence: float = 0.0
    total_market: int = 0
    scan_target: int = 0
    done: int = 0
    signals_this_cycle: int = 0
    signals_today: int = 0
    daily_signal_target: int = 5
    last_symbol: str = ""
    closest: list[str] = field(default_factory=list)
    closest_why: str = ""
    last_signal: str = "none yet"
    last_error: str = ""
    cycle_started_at: float = 0.0
    waiting_until: float = 0.0
    started_at: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key) and key != "_lock":
                    setattr(self, key, value)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "phase": self.phase,
                "cycle": self.cycle,
                "mode": self.mode,
                "min_confidence": self.min_confidence,
                "total_market": self.total_market,
                "scan_target": self.scan_target,
                "done": self.done,
                "signals_this_cycle": self.signals_this_cycle,
                "signals_today": self.signals_today,
                "daily_signal_target": self.daily_signal_target,
                "last_symbol": self.last_symbol,
                "closest": list(self.closest),
                "closest_why": self.closest_why,
                "last_signal": self.last_signal,
                "last_error": self.last_error,
                "cycle_started_at": self.cycle_started_at,
                "waiting_until": self.waiting_until,
                "started_at": self.started_at,
            }

    def format_message(self) -> str:
        s = self.snapshot()
        uptime = int(time.time() - s["started_at"])
        uh, rem = divmod(uptime, 3600)
        um, us = divmod(rem, 60)

        if s["phase"] == "scanning" and s["scan_target"]:
            pct = 100.0 * s["done"] / max(s["scan_target"], 1)
            progress = f"{s['done']}/{s['scan_target']} ({pct:.1f}%)"
        elif s["phase"] == "waiting":
            left = max(0, int(s["waiting_until"] - time.time()))
            progress = f"waiting {left // 60}m {left % 60}s until next scan"
        else:
            progress = s["phase"]

        closest = s["closest"][:3] or ["none yet"]
        closest_txt = "\n".join(f"• {c}" for c in closest)
        why = s.get("closest_why") or ""

        return (
            "📊 MEXC SPOT Bot STATUS\n"
            f"State: {s['phase'].upper()}\n"
            f"Cycle: #{s['cycle']}\n"
            f"Mode: {s['mode'] or 'n/a'}\n"
            f"Min confidence: {s['min_confidence']}%\n"
            f"Progress: {progress}\n"
            f"Spot market size: {s['total_market']} pairs\n"
            f"Signals this cycle: {s['signals_this_cycle']}\n"
            f"ABOUT TO BREAKOUT today: {s['signals_today']}/{s['daily_signal_target']}\n"
            f"Last coin checked: {s['last_symbol'] or 'n/a'}\n"
            f"Last trade alert: {s['last_signal']}\n"
            f"Uptime: {uh}h {um}m {us}s\n"
            "Closest setups:\n"
            f"{closest_txt}\n"
            + (f"Why top WAIT/NO TRADE: {why}\n" if why else "")
            + "\nType status anytime for a live update."
        )


RUNTIME = RuntimeStatus()
