"""NTP-seeded Fisher-Yates randomizer.

Concrete implementation of the :class:`Randomizer` Protocol from the
domain layer. Uses :class:`random.Random` (Mersenne Twister) seeded with
the NTP-derived integer. Reproducibility: same seed -> same order.
"""

from __future__ import annotations

import random

from pick_at_random.domain.models import Dataset, Row


class NtpSeededRandomizer:
    """Permutes a Dataset's rows deterministically from an integer seed."""

    def shuffle(self, dataset: Dataset, seed: int) -> tuple[Row, ...]:
        rng = random.Random(seed)  # noqa: S311 - deterministic seed by design
        items = list(dataset.rows)
        rng.shuffle(items)
        return tuple(items)
