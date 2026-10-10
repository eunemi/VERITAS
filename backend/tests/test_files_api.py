"""Document and media intake exposed to the frontend desks."""

from __future__ import annotations

from io import BytesIO

from docx import Document

from httpx import AsyncClient


V1 = "/api/v1"


def docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("The bridge opened in March 2026.")
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def pdf_bytes() -> bytes:
    """Build a small text PDF without adding a test-only PDF writer dependency."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length 52 >>\nstream\nBT /F1 12 Tf 72 720 Td (Bridge opened in 2026.) Tj ET\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    data += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return data


async def test_docx_upload_returns_extractable_copy(client: AsyncClient) -> None:
    response = await client.post(
        f"{V1}/files/extract-text",
        files={
            "file": (
                "brief.docx",
                docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "The bridge opened in March 2026."}


async def test_pdf_upload_returns_extractable_copy(client: AsyncClient) -> None:
    response = await client.post(
        f"{V1}/files/extract-text",
        files={"file": ("brief.pdf", pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Bridge opened in 2026."}
