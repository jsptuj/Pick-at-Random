"""Unit tests for the domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pick_at_random.domain.models import Dataset, NtpDraw, ReportMetadata, Row


class TestRow:
    def test_row_stores_values_as_tuple(self) -> None:
        row = Row(values=("a", "b", "c"))
        assert row.values == ("a", "b", "c")
        assert len(row) == 3

    def test_row_is_frozen(self) -> None:
        row = Row(values=("a",))
        with pytest.raises(FrozenInstanceError):
            row.values = ("x",)  # type: ignore[misc]

    def test_rows_with_equal_values_are_equal(self) -> None:
        assert Row(values=("a", "b")) == Row(values=("a", "b"))

    def test_empty_row_is_allowed(self) -> None:
        row = Row(values=())
        assert len(row) == 0


class TestDataset:
    def test_dataset_holds_headers_and_rows(self) -> None:
        ds = Dataset(
            headers=("name", "score"),
            rows=(Row(("alice", "10")), Row(("bob", "20"))),
        )
        assert ds.column_count == 2
        assert ds.row_count == 2

    def test_dataset_rejects_empty_headers(self) -> None:
        with pytest.raises(ValueError, match="at least one header"):
            Dataset(headers=(), rows=())

    def test_dataset_rejects_row_with_wrong_arity(self) -> None:
        with pytest.raises(ValueError, match="Row 1 has 1 values, expected 2"):
            Dataset(
                headers=("a", "b"),
                rows=(Row(("x", "y")), Row(("z",))),
            )

    def test_dataset_allows_zero_rows(self) -> None:
        ds = Dataset(headers=("only",), rows=())
        assert ds.row_count == 0
        assert ds.column_count == 1

    def test_dataset_is_frozen(self) -> None:
        ds = Dataset(headers=("a",), rows=())
        with pytest.raises(FrozenInstanceError):
            ds.headers = ("b",)  # type: ignore[misc]


class TestNtpDraw:
    def _valid_draw(self) -> NtpDraw:
        return NtpDraw(
            server="time.arnes.si",
            unix_nanoseconds=1_780_000_000_000_000_000,
            iso_timestamp="2026-05-05T12:00:00.000000+00:00",
        )

    def test_seed_returns_unix_nanoseconds(self) -> None:
        draw = self._valid_draw()
        assert draw.seed == draw.unix_nanoseconds

    def test_rejects_empty_server(self) -> None:
        with pytest.raises(ValueError, match="server"):
            NtpDraw(server="", unix_nanoseconds=1, iso_timestamp="x")

    def test_rejects_non_positive_nanoseconds(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            NtpDraw(server="x", unix_nanoseconds=0, iso_timestamp="x")
        with pytest.raises(ValueError, match="positive"):
            NtpDraw(server="x", unix_nanoseconds=-1, iso_timestamp="x")

    def test_rejects_empty_iso_timestamp(self) -> None:
        with pytest.raises(ValueError, match="iso_timestamp"):
            NtpDraw(server="x", unix_nanoseconds=1, iso_timestamp="")

    def test_is_frozen(self) -> None:
        draw = self._valid_draw()
        with pytest.raises(FrozenInstanceError):
            draw.server = "evil.example"  # type: ignore[misc]


class TestReportMetadata:
    def _valid_metadata(self, **overrides: object) -> ReportMetadata:
        defaults: dict[str, object] = {
            "hostname": "ws-001",
            "username": "blaz",
            "local_iso_timestamp": "2026-05-05T14:32:00+02:00",
            "workflow_description": "opis",
            "ntp_draw": NtpDraw(
                server="time.arnes.si",
                unix_nanoseconds=1_780_000_000_000_000_000,
                iso_timestamp="2026-05-05T12:00:00+00:00",
            ),
            "original_headers": ("name", "score"),
        }
        defaults.update(overrides)
        return ReportMetadata(**defaults)  # type: ignore[arg-type]

    def test_constructs_with_valid_inputs(self) -> None:
        meta = self._valid_metadata()
        assert meta.hostname == "ws-001"
        assert meta.original_headers == ("name", "score")

    @pytest.mark.parametrize(
        "field_name",
        ["local_iso_timestamp", "workflow_description"],
    )
    def test_rejects_empty_required_string(self, field_name: str) -> None:
        with pytest.raises(ValueError, match=field_name):
            self._valid_metadata(**{field_name: ""})

    @pytest.mark.parametrize("field_name", ["hostname", "username"])
    def test_allows_none_for_optional_identity_fields(self, field_name: str) -> None:
        meta = self._valid_metadata(**{field_name: None})
        assert getattr(meta, field_name) is None

    def test_rejects_empty_headers(self) -> None:
        with pytest.raises(ValueError, match="original_headers"):
            self._valid_metadata(original_headers=())

    def test_is_frozen(self) -> None:
        meta = self._valid_metadata()
        with pytest.raises(FrozenInstanceError):
            meta.hostname = "other"  # type: ignore[misc]
