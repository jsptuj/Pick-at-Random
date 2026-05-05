"""Unit tests for SniffingCsvReader."""

from __future__ import annotations

from pathlib import Path

import pytest

from pick_at_random.domain.models import Row
from pick_at_random.infrastructure.csv_reader import SniffingCsvReader


def _write(tmp_path: Path, name: str, content: str, *, encoding: str = "utf-8") -> str:
    p = tmp_path / name
    p.write_text(content, encoding=encoding)
    return str(p)


class TestSniffingCsvReader:
    def test_reads_comma_delimited(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "comma.csv",
            "name,score\nalice,10\nbob,20\n",
        )
        ds = SniffingCsvReader().read(path)
        assert ds.headers == ("name", "score")
        assert ds.rows == (Row(("alice", "10")), Row(("bob", "20")))

    def test_reads_semicolon_delimited(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "semi.csv",
            "ime;mesto;starost\nana;Ptuj;30\nbojan;Maribor;25\n",
        )
        ds = SniffingCsvReader().read(path)
        assert ds.headers == ("ime", "mesto", "starost")
        assert ds.row_count == 2

    def test_reads_tab_delimited(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "tab.csv",
            "a\tb\tc\n1\t2\t3\n",
        )
        ds = SniffingCsvReader().read(path)
        assert ds.headers == ("a", "b", "c")
        assert ds.rows == (Row(("1", "2", "3")),)

    def test_strips_utf8_bom(self, tmp_path: Path) -> None:
        p = tmp_path / "bom.csv"
        p.write_bytes(b"\xef\xbb\xbfname,age\nana,30\n")
        ds = SniffingCsvReader().read(str(p))
        assert ds.headers == ("name", "age")

    def test_handles_slovenian_characters(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "sl.csv",
            "ime,naslov\nČrt,Šentilj\nŽana,Češča vas\n",
        )
        ds = SniffingCsvReader().read(path)
        assert ds.rows[0].values == ("Črt", "Šentilj")
        assert ds.rows[1].values == ("Žana", "Češča vas")

    def test_dataset_with_zero_rows_is_allowed(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "headers_only.csv", "a,b,c\n")
        ds = SniffingCsvReader().read(path)
        assert ds.row_count == 0
        assert ds.column_count == 3

    def test_strips_header_whitespace(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "ws.csv", " name , score \nalice,10\n")
        ds = SniffingCsvReader().read(path)
        assert ds.headers == ("name", "score")

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            SniffingCsvReader().read(str(tmp_path / "nope.csv"))

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "empty.csv", "")
        with pytest.raises(ValueError, match="empty"):
            SniffingCsvReader().read(path)

    def test_blank_header_raises(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "blank.csv", "   \nfoo,bar\n")
        with pytest.raises(ValueError):
            SniffingCsvReader().read(path)
