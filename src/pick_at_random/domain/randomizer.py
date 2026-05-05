"""The Randomizer port and the Slovenian description of the workflow.

Implementations live in ``infrastructure``. The domain layer only defines
the contract: given a Dataset and an integer seed, produce a deterministic
permutation of the rows.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pick_at_random.domain.models import Dataset, Row


@runtime_checkable
class Randomizer(Protocol):
    """Produces a permutation of a Dataset's rows from an integer seed.

    The contract is intentionally pure: same dataset + same seed must yield
    the same row order. The seed is supplied by an :class:`NtpDraw`.
    """

    def shuffle(self, dataset: Dataset, seed: int) -> tuple[Row, ...]:
        ...


NTP_SEEDED_DESCRIPTION_SL: str = (
    "Naključno razvrščanje s pomočjo časovnega žiga, pridobljenega z "
    "uradnega strežnika NTP. Časovni žig se v polni ločljivosti pretvori "
    "v 64-bitno celo število (nanosekunde od epohe Unix) in se uporabi "
    "kot seme generatorja Mersenne Twister, ki poganja Fisher–Yatesovo "
    "premešanje vrstic. Ob enakem semenu je razvrstitev v celoti "
    "ponovljiva; strežnik, surov časovni žig in seme so zapisani v tem "
    "poročilu."
)
"""Slovenian, audit-friendly description of the randomization workflow.

This string is rendered verbatim into every PDF so that an auditor can
understand and reproduce the draw. Reviewed by a Slovenian speaker before
release; do not paraphrase casually.
"""
