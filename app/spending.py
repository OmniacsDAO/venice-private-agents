"""
Agent spending controls — human-set boundaries for autonomous spending.

The agent operates within spending limits set by the human operator.
This is a core requirement of the "agents that pay" theme: transparent,
scoped spending permissions that the agent cannot exceed.
"""

import os
import threading
from dataclasses import dataclass, field


@dataclass
class SpendingLedger:
    """Thread-safe spending tracker with human-set limits."""

    max_per_analysis: float = 0.50
    max_total: float = 10.00
    total_spent: float = 0.0
    analyses_completed: int = 0
    verdicts_published: int = 0
    reports_stored: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def can_spend(self, amount: float) -> bool:
        """Check if spending is within limits."""
        with self._lock:
            return (self.total_spent + amount) <= self.max_total

    def record_spend(self, amount: float, category: str = "") -> None:
        """Record a spend. Raises if limit would be exceeded."""
        with self._lock:
            if (self.total_spent + amount) > self.max_total:
                raise SpendingLimitExceeded(
                    f"Would exceed total budget: "
                    f"${self.total_spent:.2f} + ${amount:.2f} > "
                    f"${self.max_total:.2f}"
                )
            self.total_spent += amount

    def record_analysis(self) -> None:
        with self._lock:
            self.analyses_completed += 1

    def record_verdict(self) -> None:
        with self._lock:
            self.verdicts_published += 1

    def record_stored(self) -> None:
        with self._lock:
            self.reports_stored += 1

    @property
    def remaining(self) -> float:
        with self._lock:
            return max(0, self.max_total - self.total_spent)


class SpendingLimitExceeded(Exception):
    pass


# Singleton ledger — initialized from env vars
_ledger = None


def get_ledger() -> SpendingLedger:
    global _ledger
    if _ledger is None:
        _ledger = SpendingLedger(
            max_per_analysis=float(
                os.getenv("MAX_SPEND_PER_ANALYSIS", "0.50")
            ),
            max_total=float(os.getenv("MAX_TOTAL_SPEND", "10.00")),
        )
    return _ledger
