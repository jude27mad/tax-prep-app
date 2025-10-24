import io

import pytest
from starlette.datastructures import UploadFile

from app.ui.slip_ingest import ingest_slip_uploads


def _blank_pdf_bytes() -> bytes:
    header = b"%PDF-1.4\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << >> >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]

    parts: list[bytes] = [header]
    offsets: list[int] = [0]
    for index, obj in enumerate(objects, start=1):
        offset = sum(len(part) for part in parts)
        offsets.append(offset)
        parts.append(f"{index} 0 obj\n".encode("ascii"))
        parts.append(obj)
        parts.append(b"\nendobj\n")

    xref_offset = sum(len(part) for part in parts)
    parts.append(b"xref\n")
    parts.append(f"0 {len(objects) + 1}\n".encode("ascii"))
    parts.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        parts.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    parts.append(b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n")
    parts.append(f"{xref_offset}\n".encode("ascii"))
    parts.append(b"%%EOF\n")

    return b"".join(parts)


@pytest.mark.asyncio()
async def test_ingest_text_slip_detects_fields():
    content = (
        b"T4 Statement of Remuneration Paid\n"
        b"Box 14 Employment income: $55,123.45\n"
        b"Box 22 Income tax deducted 8,765.43\n"
        b"CPP contributions (Box 16) 3,000.99\n"
        b"EI premiums Box 18 890.12\n"
        b"Box 26 Pensionable earnings 55123.45\n"
        b"Box 24 Insurable earnings 55123.45\n"
    )
    upload = UploadFile(filename="t4_slip.txt", file=io.BytesIO(content))

    detections, errors = await ingest_slip_uploads([upload])

    assert errors == []
    assert len(detections) == 1
    fields = detections[0].fields
    assert fields["employment_income"] == "55123.45"
    assert fields["tax_deducted"] == "8765.43"
    assert fields["cpp_contrib"] == "3000.99"
    assert fields["ei_premiums"] == "890.12"
    assert fields["pensionable_earnings"] == "55123.45"
    assert fields["insurable_earnings"] == "55123.45"


@pytest.mark.asyncio()
async def test_ingest_unsupported_file_warns():
    upload = UploadFile(filename="t4_scan.jpg", file=io.BytesIO(b"\xff\xd8\xff\xe0binary-data"))

    detections, errors = await ingest_slip_uploads([upload])

    assert errors == []
    assert len(detections) == 1
    detection = detections[0]
    assert detection.fields == {}
    assert detection.warnings  # expect unsupported format warning


@pytest.mark.asyncio()
async def test_ingest_scanned_pdf_triggers_ocr(monkeypatch):
    pdf_bytes = _blank_pdf_bytes()
    upload = UploadFile(filename="scanned_t4.pdf", file=io.BytesIO(pdf_bytes))

    sentinel = object()
    calls: dict[str, bool] = {"rasterize": False, "ocr": False}

    def fake_rasterize(data: bytes):  # type: ignore[no-untyped-def]
        assert data == pdf_bytes
        calls["rasterize"] = True
        return [sentinel]

    def fake_ocr(images):  # type: ignore[no-untyped-def]
        assert list(images) == [sentinel]
        calls["ocr"] = True
        return [
            "T4 Statement of Remuneration Paid\n"
            "Box 14 Employment income: 55,123.45\n"
            "Box 22 Income tax deducted 8,765.43\n"
        ]

    monkeypatch.setattr("app.ui.slip_ingest._rasterize_pdf", fake_rasterize)
    monkeypatch.setattr("app.ui.slip_ingest._perform_pdf_ocr", fake_ocr)

    detections, errors = await ingest_slip_uploads([upload])

    assert errors == []
    assert calls["rasterize"]
    assert calls["ocr"]
    assert len(detections) == 1
    detection = detections[0]
    fields = detection.fields
    assert fields["employment_income"] == "55123.45"
    assert fields["tax_deducted"] == "8765.43"
