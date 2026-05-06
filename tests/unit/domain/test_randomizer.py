"""Unit tests for the Randomizer protocol and its workflow description."""

from __future__ import annotations

import random

from pick_at_random.domain.models import Dataset, Row
from pick_at_random.domain.randomizer import (
    NTP_SEEDED_DESCRIPTION_SL,
    Randomizer,
)


class _SeededFisherYates:
    """Reference implementation used to validate the protocol contract.

    The real adapter lives in infrastructure; this fake exists only so the
    domain test suite can exercise the protocol's deterministic-seed
    contract without importing third-party code.
    """

    def shuffle(self, dataset: Dataset, seed: int) -> tuple[Row, ...]:
        rng = random.Random(seed)  # noqa: S311 - deterministic test fake
        items = list(dataset.rows)
        rng.shuffle(items)
        return tuple(items)


class TestRandomizerProtocol:
    def test_fake_implementation_satisfies_protocol(self) -> None:
        impl: Randomizer = _SeededFisherYates()
        assert isinstance(impl, Randomizer)

    def test_same_seed_produces_same_order(self) -> None:
        ds = Dataset(
            headers=("v",),
            rows=tuple(Row((str(i),)) for i in range(20)),
        )
        impl = _SeededFisherYates()
        first = impl.shuffle(ds, seed=42)
        second = impl.shuffle(ds, seed=42)
        assert first == second

    def test_different_seeds_typically_produce_different_orders(self) -> None:
        ds = Dataset(
            headers=("v",),
            rows=tuple(Row((str(i),)) for i in range(20)),
        )
        impl = _SeededFisherYates()
        a = impl.shuffle(ds, seed=1)
        b = impl.shuffle(ds, seed=2)
        assert a != b

    def test_shuffle_preserves_membership(self) -> None:
        ds = Dataset(
            headers=("v",),
            rows=tuple(Row((str(i),)) for i in range(50)),
        )
        impl = _SeededFisherYates()
        result = impl.shuffle(ds, seed=12345)
        assert sorted(result, key=lambda r: r.values) == sorted(ds.rows, key=lambda r: r.values)
        assert len(result) == ds.row_count

    def test_empty_dataset_returns_empty_tuple(self) -> None:
        ds = Dataset(headers=("v",), rows=())
        impl = _SeededFisherYates()
        assert impl.shuffle(ds, seed=99) == ()

    def test_single_row_returns_unchanged(self) -> None:
        ds = Dataset(headers=("v",), rows=(Row(("only",)),))
        impl = _SeededFisherYates()
        assert impl.shuffle(ds, seed=99) == (Row(("only",)),)


class TestSlovenianDescription:
    def test_description_is_non_empty_string(self) -> None:
        assert isinstance(NTP_SEEDED_DESCRIPTION_SL, str)
        assert len(NTP_SEEDED_DESCRIPTION_SL) > 0

    def test_description_mentions_ntp(self) -> None:
        assert "NTP" in NTP_SEEDED_DESCRIPTION_SL

    def test_description_mentions_fisher_yates(self) -> None:
        assert "Fisher" in NTP_SEEDED_DESCRIPTION_SL
