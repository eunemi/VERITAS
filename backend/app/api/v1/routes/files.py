"""Safe file intake for text extraction and media examination."""

from __future__ import annotations

import codecs
import io
import mimetypes
import re
import zipfile
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from uuid import uuid4

import anyio
import anyio.to_thread
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import SettingsDep
from app.core.errors import PayloadTooLargeError

router = APIRouter(prefix="/files", tags=["files"])

TEXT_EXTENSIONS = frozenset({".md", ".pdf", ".docx", ".txt"})
MEDIA_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".avif",
    }
)
_STORED_NAME = re.compile(r"^[0-9a-f]{32}(?:\.[a-z0-9]{1,10})?$")
# These defaults mirror Settings, while keeping the parser useful away from FastAPI
# (for example in a worker or a focused unit test). Routes pass deployment values.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
MAX_PDF_PAGES = 500
MAX_PDF_CONTENT_STREAM_BYTES = 8 * 1024 * 1024
MAX_ZIP_MEMBERS = 2048
_ZIP_READ_CHUNK = 64 * 1024

# Reading, decoding, and storing a document or image is CPU- and memory-heavy. Keep
# the complete upload operation bounded independently of the verification runner so
# completed reads cannot accumulate while one artifact is being processed.
_FILE_WORK = anyio.CapacityLimiter(1)


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(
                "The uploaded file exceeds the configured size limit.",
                details={"limit": limit},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _extension(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was uploaded.")
    return Path(file.filename).suffix.lower()


@router.post("/extract-text")
async def extract_text(
    settings: SettingsDep,
    file: UploadFile = File(...),  # noqa: B008
) -> dict[str, str]:
    """Extract prose from TXT, Markdown, PDF, or DOCX within the byte cap."""
    try:
        extension = _extension(file)
        if extension not in TEXT_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail="Upload a TXT, Markdown, PDF, or DOCX document.",
            )
        async with _FILE_WORK:
            content = await _read_limited(file, settings.MAX_UPLOAD_BYTES)
            if extension in {".md", ".txt"}:
                try:
                    text = await anyio.to_thread.run_sync(
                        _decode_text, content, settings.MAX_TEXT_CHARS
                    )
                except UnicodeDecodeError as exc:
                    raise HTTPException(
                        status_code=400, detail="Text files must use UTF-8 encoding."
                    ) from exc
            else:
                text = await anyio.to_thread.run_sync(
                    partial(
                        _extract_document,
                        content,
                        extension,
                        settings.MAX_TEXT_CHARS,
                        settings.MAX_UPLOAD_BYTES,
                    )
                )
            text = text.strip()
            if not text:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "The document contains no embedded text. Scanned PDFs need OCR "
                        "before they can be verified."
                    ),
                )
        return {"text": text}
    finally:
        await file.close()


@router.post("/upload-media", status_code=status.HTTP_201_CREATED)
async def upload_media(
    settings: SettingsDep,
    file: UploadFile = File(...),  # noqa: B008
) -> dict[str, str]:
    """Store accepted media and return an API-served URL for verification."""
    try:
        extension = _extension(file)
        if extension not in MEDIA_EXTENSIONS:
            raise HTTPException(
                status_code=415, detail="Upload a supported image file."
            )
        async with _FILE_WORK:
            content = await _read_limited(file, settings.MAX_UPLOAD_BYTES)
            from app.vision.context import validate

            # Validation checks the source without producing a normalized copy. The
            # exact submitted bytes are what the later desk fetches and records.
            await anyio.to_thread.run_sync(validate, content)
            directory = Path(settings.UPLOAD_DIRECTORY).resolve()  # noqa: ASYNC240
            stored_name = f"{uuid4().hex}{extension}"
            await anyio.to_thread.run_sync(
                _store_upload, directory, stored_name, content
            )
        return {
            "url": (
                f"{settings.PUBLIC_API_URL.rstrip('/')}"
                f"{settings.API_V1_PREFIX}/files/media/{stored_name}"
            )
        }
    finally:
        await file.close()


def _decode_text(content: bytes, limit: int) -> str:
    """Decode UTF-8 incrementally so a giant text upload stops at the text cap."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    pieces: list[str] = []
    characters = 0
    for offset in range(0, len(content), 64 * 1024):
        piece = decoder.decode(content[offset : offset + 64 * 1024], final=False)
        characters += len(piece)
        if characters > limit:
            raise PayloadTooLargeError(
                "The extracted document text exceeds the configured character limit.",
                details={"limit": limit},
            )
        pieces.append(piece)
    tail = decoder.decode(b"", final=True)
    characters += len(tail)
    if characters > limit:
        raise PayloadTooLargeError(
            "The extracted document text exceeds the configured character limit.",
            details={"limit": limit},
        )
    pieces.append(tail)
    return "".join(pieces)


def _extract_document(
    content: bytes,
    extension: str,
    max_text_chars: int = MAX_TEXT_CHARS,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
) -> str:
    """Parse a document off the event loop without unbounded package expansion."""
    try:
        if extension == ".pdf":
            return _extract_pdf(content, max_text_chars)

        import docx

        _check_docx_archive(content, max_upload_bytes)
        accumulator = _TextAccumulator(max_text_chars)
        with io.BytesIO(content) as stream:
            document = docx.Document(stream)
            _append_container_text(document, accumulator)
            for section in document.sections:
                if not section.header.is_linked_to_previous:
                    _append_container_text(section.header, accumulator)
                if not section.footer.is_linked_to_previous:
                    _append_container_text(section.footer, accumulator)
        return accumulator.text
    except (HTTPException, PayloadTooLargeError):
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail="The document could not be read."
        ) from exc


def _extract_pdf(content: bytes, max_text_chars: int) -> str:
    from pypdf import PdfReader

    accumulator = _TextAccumulator(max_text_chars)
    with io.BytesIO(content) as stream:
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted:
            raise HTTPException(
                status_code=422,
                detail="Encrypted PDFs are not supported; upload an unencrypted copy.",
            )
        pages = reader.pages
        if len(pages) > MAX_PDF_PAGES:
            raise PayloadTooLargeError(
                "The PDF contains too many pages to extract safely.",
                details={"limit": MAX_PDF_PAGES},
            )
        for page in pages:
            _check_pdf_content_stream(page, MAX_PDF_CONTENT_STREAM_BYTES)
            accumulator.add(page.extract_text() or "")
    return accumulator.text


def _check_pdf_content_stream(page: object, limit: int) -> None:
    """Reject pages with oversized raw content streams before text extraction."""
    contents = page.get("/Contents")  # type: ignore[attr-defined]
    if contents is None:
        return
    contents = contents.get_object()
    streams = contents if isinstance(contents, list) else [contents]
    total = 0
    for item in streams:
        stream = item.get_object()
        declared = stream.get("/Length", 0)
        resolve = getattr(declared, "get_object", None)
        if callable(resolve):
            declared = resolve()
        total += declared if isinstance(declared, int) else 0
        if total > limit:
            raise PayloadTooLargeError(
                "The PDF page content exceeds the configured extraction limit.",
                details={"limit": limit},
            )


def _check_docx_archive(content: bytes, max_uncompressed_bytes: int) -> None:
    """Reject encrypted and expansion-heavy DOCX packages before python-docx reads."""
    with io.BytesIO(content) as stream, zipfile.ZipFile(stream) as archive:
        members = archive.infolist()
        if len(members) > MAX_ZIP_MEMBERS:
            raise PayloadTooLargeError(
                "The DOCX package contains too many archive members.",
                details={"limit": MAX_ZIP_MEMBERS},
            )

        for member in members:
            if member.flag_bits & 0x1:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Encrypted DOCX files are not supported; upload an "
                        "unencrypted copy."
                    ),
                )

        total = 0
        for member in members:
            if member.is_dir():
                continue
            with archive.open(member) as entry:
                while chunk := entry.read(_ZIP_READ_CHUNK):
                    total += len(chunk)
                    if total > max_uncompressed_bytes:
                        raise PayloadTooLargeError(
                            "The DOCX package would expand beyond the configured "
                            "upload limit.",
                            details={"limit": max_uncompressed_bytes},
                        )


class _TextAccumulator:
    """Append logical blocks while retaining at most the configured text."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._parts: list[str] = []
        self._length = 0

    def add(self, value: object) -> None:
        text = str(value).strip()
        if not text:
            return
        extra = len(text) + (1 if self._parts else 0)
        if self._length + extra > self._limit:
            raise PayloadTooLargeError(
                "The extracted document text exceeds the configured character limit.",
                details={"limit": self._limit},
            )
        self._parts.append(text)
        self._length += extra

    @property
    def text(self) -> str:
        return "\n".join(self._parts)

    @property
    def parts(self) -> list[str]:
        return self._parts.copy()


def _append_container_text(container: object, accumulator: _TextAccumulator) -> None:
    for block in _iter_blocks(container):
        if hasattr(block, "rows"):
            for row_text in _table_rows_text(block):
                accumulator.add(row_text)
        else:
            accumulator.add(getattr(block, "text", ""))


def _table_rows_text(table: object) -> list[str]:
    """Flatten a table without repeating merged cells or losing nested tables."""
    seen_cells: set[int] = set()
    rows: list[str] = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            cell_id = id(cell._tc)
            if cell_id in seen_cells:
                continue
            seen_cells.add(cell_id)
            text = _cell_text(cell)
            if text:
                cells.append(text)
        if cells:
            rows.append(" | ".join(cells))
    return rows


def _cell_text(cell: object) -> str:
    parts: list[str] = []
    for block in _iter_blocks(cell):
        if hasattr(block, "rows"):
            parts.extend(_table_rows_text(block))
        else:
            text = getattr(block, "text", "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _container_text(container: object) -> list[str]:
    """Return a bounded container's blocks, retaining their document order."""
    accumulator = _TextAccumulator(MAX_TEXT_CHARS)
    _append_container_text(container, accumulator)
    return accumulator.parts


def _iter_blocks(container: object) -> Iterator[object]:
    iterator = getattr(container, "iter_inner_content", None)
    if callable(iterator):
        yield from iterator()
        return

    # python-docx 1.2 has iter_inner_content; this fallback keeps the parser safe
    # on older deployments without reverting to paragraph-then-table ordering.
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    element = container._element
    for child in element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, container)
        elif isinstance(child, CT_Tbl):
            yield Table(child, container)


def _store_upload(directory: Path, filename: str, content: bytes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(content)


@router.get("/media/{filename}")
async def get_media(filename: str, settings: SettingsDep) -> FileResponse:
    """Serve only opaque generated names; user paths are never interpolated."""
    if not _STORED_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="File not found.")
    path = Path(settings.UPLOAD_DIRECTORY).resolve() / filename  # noqa: ASYNC240
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")
