"""Unit tests for NtpSeededRandomizer."""

from __future__ import annotations

from collections import Counter

from pick_at_random.domain.models import Dataset, Row
from pick_at_random.infrastructure.randomizer import NtpSeededRandomizer


def _dataset(n: int) -> Dataset:
    return Dataset(headers=("v",), rows=tuple(Row((str(i),)) for i in range(n)))


class TestNtpSeededRandomizer:
    def test_same_seed_produces_same_order(self) -> None:
        ds = _dataset(20)
        r = NtpSeededRandomizer()
        assert r.shuffle(ds, seed=12345) == r.shuffle(ds, seed=12345)

    def test_different_seeds_typically_differ(self) -> None:
        ds = _dataset(20)
        r = NtpSeededRandomizer()
        assert r.shuffle(ds, seed=1) != r.shuffle(ds, seed=2)

    def test_membership_preserved(self) -> None:
        ds = _dataset(50)
        r = NtpSeededRandomizer()
        out = r.shuffle(ds, seed=7)
        assert Counter(out) == Counter(ds.rows)
        assert len(out) == ds.row_count

    def test_empty_dataset(self) -> None:
        ds = Dataset(headers=("a",), rows=())
        assert NtpSeededRandomizer().shuffle(ds, seed=1) == ()

    def test_single_row(self) -> None:
        only = Row(("x",))
        ds = Dataset(headers=("a",), rows=(only,))
        assert NtpSeededRandomizer().shuffle(ds, seed=1) == (only,)
