"""Time-based pet needs: hunger, thirst, play, and cuddle.

Each need accumulates over real time.  ``level()`` returns 0.0 (fresh) to 1.0
(critical).  Call the corresponding ``satisfy_*`` method to reset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Need:
    """A single dimension of cat wellness."""

    threshold: float          # seconds until the need becomes active (level >= 1.0)
    last_satisfied: float     # absolute time (seconds since epoch or clock start)

    def level(self, now: float) -> float:
        """0.0 = fresh, 1.0 = threshold reached, >1.0 = overdue."""
        elapsed = now - self.last_satisfied
        return elapsed / self.threshold if self.threshold > 0 else 0.0

    def is_active(self, now: float) -> bool:
        return self.level(now) >= 1.0

    def satisfy(self, now: float) -> None:
        self.last_satisfied = now


@dataclass
class PetNeeds:
    """All four pet-wellness dimensions."""

    hunger: Need = field(default_factory=lambda: Need(threshold=3600.0, last_satisfied=0.0))
    thirst: Need = field(default_factory=lambda: Need(threshold=1800.0, last_satisfied=0.0))
    play: Need = field(default_factory=lambda: Need(threshold=900.0, last_satisfied=0.0))
    cuddle: Need = field(default_factory=lambda: Need(threshold=1200.0, last_satisfied=0.0))

    def reset(self, now: float) -> None:
        """Initialise all last_satisfied timestamps to now."""
        for n in (self.hunger, self.thirst, self.play, self.cuddle):
            n.last_satisfied = now

    def most_urgent(self, now: float) -> str | None:
        """Name of the most overdue active need, or None if all satisfied."""
        candidates = [
            (self.hunger.level(now), "hunger"),
            (self.thirst.level(now), "thirst"),
            (self.play.level(now), "play"),
            (self.cuddle.level(now), "cuddle"),
        ]
        active = [(lvl, name) for lvl, name in candidates if lvl >= 1.0]
        if not active:
            return None
        return max(active)[1]

    def starvation_scale(self, now: float, onset: float = 7200.0) -> float:
        """Horizontal squeeze factor (1.0 = normal, 0.7 = visibly thin).

        The cat starts looking thin ``onset`` seconds after hunger threshold.
        """
        overdue = (now - self.hunger.last_satisfied) - self.hunger.threshold
        if overdue <= 0:
            return 1.0
        ratio = min(overdue / onset, 1.0)
        return 1.0 - 0.3 * ratio
