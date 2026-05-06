"""ReportLab-based PdfWriter rendering Slovenian content.

The output is a single A4 portrait document containing:

* Title (`"Naključna razvrstitev"`).
* A two-column metadata table: hostname, username, local execution time
  (formatted in `sl_SI` via Babel), workflow description. Hostname and
  username rows are omitted when their values are missing.
* An NTP draw block: server, raw ISO timestamp, derived integer seed.
* The shuffled rows rendered under the original CSV headers, with an
  ordinal "Zaporedna št." column prepended. The header row repeats on
  every page the table spans.
* A trailing "Digitalni podpis" section (subject CN, issuer CN,
  validity range) — placed at the very end of the document so the
  results table follows immediately after the metadata.

ReportLab's standard 14 PostScript fonts (Helvetica/Times/Courier) cover
only WinAnsi, which lacks Č/č. The PDF therefore uses Bitstream Vera
Sans, which ships with ReportLab and covers Latin Extended-A.

The PDF leaves space at the bottom for the digital signature; the
signature itself is added later by the :class:`Signer` adapter.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from babel.dates import format_datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from pick_at_random.domain.models import ReportMetadata, Row

_LABEL_TITLE = "Naključna razvrstitev seznama - žreb"
_LABEL_HOSTNAME = "Računalnik:"
_LABEL_USERNAME = "Uporabnik:"
_LABEL_LOCAL_TIME = "Čas izvedbe:"
_LABEL_SOURCE_FILE = "Vhodna datoteka:"
_LABEL_WORKFLOW = "Opis postopka:"
_LABEL_NTP_BLOCK = "Vir naključja (NTP)"
_LABEL_NTP_SERVER = "Strežnik:"
_LABEL_NTP_TIMESTAMP = "Časovni žig:"
_LABEL_NTP_SEED = "Seme (ns):"
_LABEL_CERT_BLOCK = "Digitalni podpis"
_LABEL_CERT_SUBJECT = "Imetnik (CN):"
_LABEL_CERT_ISSUER = "Izdajatelj (CN):"
_LABEL_CERT_VALID_FROM = "Veljavnost od:"
_LABEL_CERT_VALID_TO = "Veljavnost do:"
_LABEL_RESULTS = "Naključno razvrščeni vnosi"
_LABEL_ORDINAL = "Zap. št."
_LABEL_EMPTY = "(brez vnosov)"
_LABEL_AUTHOR = "Pick at Random"

_FONT_REGULAR = "PickVeraSans"
_FONT_BOLD = "PickVeraSans-Bold"
_FONT_REGULAR_FILE = "Vera.ttf"
_FONT_BOLD_FILE = "VeraBd.ttf"

_font_lock = threading.Lock()
_fonts_registered = False


def _register_fonts() -> None:
    """Register Bitstream Vera Sans (regular + bold) once per process.

    The TTFs ship with ReportLab and live on its default search path, so
    no extra files need to be bundled with this project.
    """
    global _fonts_registered
    if _fonts_registered:
        return
    with _font_lock:
        if _fonts_registered:
            return
        pdfmetrics.registerFont(TTFont(_FONT_REGULAR, _FONT_REGULAR_FILE))
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, _FONT_BOLD_FILE))
        pdfmetrics.registerFontFamily(
            _FONT_REGULAR,
            normal=_FONT_REGULAR,
            bold=_FONT_BOLD,
        )
        _fonts_registered = True


class ReportLabPdfWriter:
    """Renders the unsigned PDF report using ReportLab Platypus."""

    def __init__(self, locale: str = "sl_SI") -> None:
        if not locale:
            raise ValueError("locale must be non-empty.")
        self._locale = locale

    def write(
        self,
        destination: str,
        shuffled_rows: tuple[Row, ...],
        metadata: ReportMetadata,
    ) -> None:
        _register_fonts()

        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=24 * mm,
            title=_LABEL_TITLE,
            author=_LABEL_AUTHOR,
        )
        sample = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title",
            parent=sample["Title"],
            fontName=_FONT_BOLD,
            alignment=1,
            fontSize=18,
            spaceAfter=8,
        )
        section_style = ParagraphStyle(
            "Section",
            parent=sample["Heading2"],
            fontName=_FONT_BOLD,
            fontSize=12,
            spaceBefore=10,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "Body",
            parent=sample["BodyText"],
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=13,
        )

        story: list[object] = [
            Paragraph(_LABEL_TITLE, title_style),
            Spacer(1, 4 * mm),
            self._metadata_table(metadata, body_style),
            Spacer(1, 4 * mm),
            Paragraph(_LABEL_WORKFLOW, section_style),
            Paragraph(metadata.workflow_description, body_style),
            Spacer(1, 4 * mm),
            Paragraph(_LABEL_NTP_BLOCK, section_style),
            self._ntp_table(metadata, body_style),
            Spacer(1, 6 * mm),
            Paragraph(_LABEL_RESULTS, section_style),
            self._results_block(metadata, shuffled_rows, body_style),
        ]
        cert_table = self._certificate_table(metadata, body_style)
        if cert_table is not None:
            story.append(Spacer(1, 6 * mm))
            story.append(Paragraph(_LABEL_CERT_BLOCK, section_style))
            story.append(cert_table)
        doc.build(story)

    def _metadata_table(self, metadata: ReportMetadata, body: ParagraphStyle) -> Table:
        local_human = self._format_local_time(metadata.local_iso_timestamp)
        rows: list[list[Paragraph]] = []
        if metadata.hostname:
            rows.append([Paragraph(_LABEL_HOSTNAME, body), Paragraph(metadata.hostname, body)])
        if metadata.username:
            rows.append([Paragraph(_LABEL_USERNAME, body), Paragraph(metadata.username, body)])
        rows.append([Paragraph(_LABEL_LOCAL_TIME, body), Paragraph(local_human, body)])
        if metadata.source_filename:
            rows.append(
                [
                    Paragraph(_LABEL_SOURCE_FILE, body),
                    Paragraph(metadata.source_filename, body),
                ]
            )
        return self._label_value_table(rows)

    def _certificate_table(self, metadata: ReportMetadata, body: ParagraphStyle) -> Table | None:
        info = metadata.certificate_info
        if info is None:
            return None
        rows: list[list[Paragraph]] = []
        if info.subject_cn:
            rows.append([Paragraph(_LABEL_CERT_SUBJECT, body), Paragraph(info.subject_cn, body)])
        if info.issuer_cn:
            rows.append([Paragraph(_LABEL_CERT_ISSUER, body), Paragraph(info.issuer_cn, body)])
        if info.valid_from_iso:
            rows.append(
                [
                    Paragraph(_LABEL_CERT_VALID_FROM, body),
                    Paragraph(info.valid_from_iso, body),
                ]
            )
        if info.valid_to_iso:
            rows.append([Paragraph(_LABEL_CERT_VALID_TO, body), Paragraph(info.valid_to_iso, body)])
        if not rows:
            return None
        return self._label_value_table(rows)

    def _ntp_table(self, metadata: ReportMetadata, body: ParagraphStyle) -> Table:
        draw = metadata.ntp_draw
        rows: list[list[Paragraph]] = [
            [Paragraph(_LABEL_NTP_SERVER, body), Paragraph(draw.server, body)],
            [
                Paragraph(_LABEL_NTP_TIMESTAMP, body),
                Paragraph(draw.iso_timestamp, body),
            ],
            [
                Paragraph(_LABEL_NTP_SEED, body),
                Paragraph(str(draw.unix_nanoseconds), body),
            ],
        ]
        return self._label_value_table(rows)

    def _results_block(
        self,
        metadata: ReportMetadata,
        shuffled_rows: tuple[Row, ...],
        body: ParagraphStyle,
    ) -> Table | Paragraph:
        if not shuffled_rows:
            return Paragraph(_LABEL_EMPTY, body)

        header_cells = [Paragraph(_LABEL_ORDINAL, body)] + [
            Paragraph(h, body) for h in metadata.original_headers
        ]
        data_rows: list[list[Paragraph]] = [header_cells]
        for index, row in enumerate(shuffled_rows, start=1):
            data_rows.append(
                [Paragraph(str(index), body)] + [Paragraph(cell, body) for cell in row.values]
            )

        # `repeatRows=1` keeps the header on every page the table spans;
        # do NOT wrap in `KeepTogether`, which would collapse the table
        # onto a single page and bypass the header repeat.
        table = Table(data_rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
                    ("FONTNAME", (0, 1), (-1, -1), _FONT_REGULAR),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table

    def _label_value_table(self, rows: list[list[Paragraph]]) -> Table:
        table = Table(rows, colWidths=[40 * mm, None], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), _FONT_BOLD),
                    ("FONTNAME", (1, 0), (1, -1), _FONT_REGULAR),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return table

    def _format_local_time(self, iso_timestamp: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_timestamp)
        except ValueError:
            return iso_timestamp
        formatted = format_datetime(dt, format="d. MMMM y, HH:mm", locale=self._locale)
        return f"{formatted} ({iso_timestamp})"
