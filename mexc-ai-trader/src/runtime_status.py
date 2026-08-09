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
    last_symbol: str = ""
    closest: list[str] = field(default_factory=list)
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
                "last_symbol": self.last_symbol,
                "closest": list(self.closest),
                "last_signal": self.last_signal,
                "last_error": self.last_error,
                "cycle_started_at": self.cycle_started_at,
                "waiting_until": self.waiting_until,
                "started_at": self.started_at,
            }

    def format_message(self) -> str:
        """Clear NFT-bot-style status card."""
        s = self.snapshot()
        uptime = int(time.time() - s["started_at"])
        uh, rem = divmod(uptime, 3600)
        um, us = divmod(rem, 60)

        if s["phase"] == "scanning" and s["scan_target"]:
            state = f"Scanning… {s['done']}/{s['scan_target']}"
        elif s["phase"] == "waiting":
            left = max(0, int(s["waiting_until"] - time.time()))
            state = f"Waiting {left // 60}m {left % 60}s for next scan"
        elif s["phase"] == "error":
            state = f"Error: {s['last_error'] or 'unknown'}"
        else:
            state = s["phase"]

        closest = s["closest"][:3] or ["none yet"]
        closest_txt = "\n".join(f"✅ {c}" if "BUY" in c or "SELL" in c else f"• {c}" for c in closest)

        return (
            "📡 Futures bot STATUS\n"
            f"State: {state}\n"
            f"Cycle: #{s['cycle']}\n"
            f"Mode: {s['mode'] or 'n/a'} | Min confidence: {s['min_confidence']:.0f}%\n"
            f"Universe: top {s['scan_target'] or 0} / {s['total_market'] or 0} pairs\n"
            f"Signals this cycle: {s['signals_this_cycle']}\n"
            f"Last alert: {s['last_signal']}\n"
            f"Last coin: {s['last_symbol'] or 'n/a'}\n"
            f"Uptime: {uh}h {um}m {us}s\n"
            "Closest setups:\n"
            f"{closest_txt}\n"
            "\nType status anytime · trade alerts send automatically"
        )


RUNTIME = RuntimeStatus()
