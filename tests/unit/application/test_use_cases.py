"""Unit tests for ShuffleAndReportUseCase."""

from __future__ import annotations

from collections import Counter

import pytest

from pick_at_random.application.use_cases import (
    ShuffleAndReportRequest,
    ShuffleAndReportUseCase,
)
from pick_at_random.domain.models import Dataset, Row
from tests.unit.application.fakes import (
    DeterministicRandomizer,
    FakeCsvReader,
    FakeTimeSource,
    FixedClock,
    FixedHostInfo,
    RecordingPdfWriter,
    RecordingSigner,
)

WORKFLOW = "Naključno razvrščanje (test)"


def _build_use_case(
    dataset: Dataset,
) -> tuple[
    ShuffleAndReportUseCase,
    FakeCsvReader,
    DeterministicRandomizer,
    RecordingPdfWriter,
    RecordingSigner,
    FakeTimeSource,
]:
    csv_reader = FakeCsvReader(dataset=dataset)
    randomizer = DeterministicRandomizer()
    pdf_writer = RecordingPdfWriter()
    signer = RecordingSigner()
    time_source = FakeTimeSource()
    use_case = ShuffleAndReportUseCase(
        csv_reader=csv_reader,
        randomizer=randomizer,
        pdf_writer=pdf_writer,
        signer=signer,
        clock=FixedClock(),
        host_info=FixedHostInfo(),
        time_source=time_source,
        workflow_description=WORKFLOW,
    )
    return use_case, csv_reader, randomizer, pdf_writer, signer, time_source


class TestHappyPath:
    def test_returns_summary_with_seed_and_server(self) -> None:
        ds = Dataset(
            headers=("name", "score"),
            rows=tuple(Row((f"name-{i}", str(i))) for i in range(5)),
        )
        use_case, *_, time_source = _build_use_case(ds)

        result = use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        assert result.pdf_path == "/out.pdf"
        assert result.row_count == 5
        assert result.seed == time_source.draw.seed
        assert result.ntp_server == "time.arnes.si"

    def test_pdf_writer_receives_shuffled_rows_and_metadata(self) -> None:
        ds = Dataset(
            headers=("name", "score"),
            rows=tuple(Row((f"name-{i}", str(i))) for i in range(5)),
        )
        use_case, _, randomizer, pdf_writer, _, time_source = _build_use_case(ds)

        use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        assert len(pdf_writer.calls) == 1
        destination, written_rows, metadata = pdf_writer.calls[0]
        assert destination == "/out.pdf"
        # Same membership as input, possibly different order.
        assert Counter(written_rows) == Counter(ds.rows)
        # Metadata is fully populated.
        assert metadata.hostname == "ws-001"
        assert metadata.username == "blaz"
        assert metadata.workflow_description == WORKFLOW
        assert metadata.original_headers == ("name", "score")
        assert metadata.ntp_draw == time_source.draw
        # Randomizer was driven by the NTP-derived seed.
        assert randomizer.calls == [(5, time_source.draw.seed)]

    def test_signer_runs_after_pdf_writer_on_same_path(self) -> None:
        ds = Dataset(headers=("a",), rows=(Row(("x",)),))
        use_case, _, _, pdf_writer, signer, _ = _build_use_case(ds)

        use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        assert pdf_writer.calls[0][0] == "/out.pdf"
        assert signer.calls == ["/out.pdf"]

    def test_csv_reader_called_once_with_request_path(self) -> None:
        ds = Dataset(headers=("a",), rows=(Row(("x",)),))
        use_case, csv_reader, *_ = _build_use_case(ds)

        use_case.execute(
            ShuffleAndReportRequest(csv_path="/some/in.csv", pdf_path="/out.pdf")
        )

        assert csv_reader.calls == ["/some/in.csv"]

    def test_time_source_called_exactly_once(self) -> None:
        ds = Dataset(headers=("a",), rows=(Row(("x",)),))
        use_case, *_, time_source = _build_use_case(ds)

        use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        assert time_source.calls == 1

    def test_same_seed_produces_same_output_order(self) -> None:
        ds = Dataset(
            headers=("v",),
            rows=tuple(Row((str(i),)) for i in range(10)),
        )
        use_case_a, *_ = _build_use_case(ds)
        use_case_b, *_ = _build_use_case(ds)

        use_case_a.execute(ShuffleAndReportRequest("/in.csv", "/a.pdf"))
        use_case_b.execute(ShuffleAndReportRequest("/in.csv", "/b.pdf"))

        # Both runs use the default fake NTP draw -> same seed -> same order.
        # We assert via the pdf_writer recordings.
        rows_a = use_case_a._pdf_writer.calls[0][1]  # type: ignore[attr-defined]
        rows_b = use_case_b._pdf_writer.calls[0][1]  # type: ignore[attr-defined]
        assert rows_a == rows_b


class TestEdgeCases:
    def test_empty_dataset_still_writes_and_signs(self) -> None:
        ds = Dataset(headers=("name",), rows=())
        use_case, _, _, pdf_writer, signer, _ = _build_use_case(ds)

        result = use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        assert result.row_count == 0
        assert pdf_writer.calls[0][1] == ()
        assert signer.calls == ["/out.pdf"]

    def test_single_row_passes_through_unchanged(self) -> None:
        only = Row(("only",))
        ds = Dataset(headers=("name",), rows=(only,))
        use_case, _, _, pdf_writer, _, _ = _build_use_case(ds)

        use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        assert pdf_writer.calls[0][1] == (only,)

    def test_duplicate_rows_are_preserved_count_wise(self) -> None:
        dup = Row(("dup",))
        ds = Dataset(
            headers=("name",),
            rows=(dup, dup, dup, Row(("uniq",))),
        )
        use_case, _, _, pdf_writer, _, _ = _build_use_case(ds)

        use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        written = pdf_writer.calls[0][1]
        assert Counter(written) == Counter(ds.rows)
        assert len(written) == 4


class TestConstruction:
    def test_rejects_empty_workflow_description(self) -> None:
        ds = Dataset(headers=("a",), rows=())
        with pytest.raises(ValueError, match="workflow_description"):
            ShuffleAndReportUseCase(
                csv_reader=FakeCsvReader(dataset=ds),
                randomizer=DeterministicRandomizer(),
                pdf_writer=RecordingPdfWriter(),
                signer=RecordingSigner(),
                clock=FixedClock(),
                host_info=FixedHostInfo(),
                time_source=FakeTimeSource(),
                workflow_description="",
            )


class TestRequestAndResult:
    def test_request_is_frozen(self) -> None:
        req = ShuffleAndReportRequest(csv_path="/a", pdf_path="/b")
        with pytest.raises(Exception):  # noqa: B017, PT011 - FrozenInstanceError-equivalent
            req.csv_path = "/c"  # type: ignore[misc]

    def test_result_carries_all_summary_fields(self) -> None:
        ds = Dataset(headers=("a",), rows=(Row(("x",)),))
        use_case, *_, time_source = _build_use_case(ds)

        result = use_case.execute(
            ShuffleAndReportRequest(csv_path="/in.csv", pdf_path="/out.pdf")
        )

        assert result == result.__class__(
            pdf_path="/out.pdf",
            row_count=1,
            seed=time_source.draw.seed,
            ntp_server="time.arnes.si",
        )
