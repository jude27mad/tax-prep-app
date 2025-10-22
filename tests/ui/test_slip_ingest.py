import io

import pytest
from starlette.datastructures import UploadFile

from app.ui.slip_ingest import ingest_slip_uploads


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
