"""Safe file intake for text extraction and media examination."""

from __future__ import annotations

import io
import mimetypes
import re
from pathlib import Path
from uuid import uuid4

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
        ".mp3",
        ".wav",
        ".m4a",
        ".ogg",
        ".aac",
        ".flac",
        ".mp4",
        ".mov",
        ".webm",
        ".mkv",
    }
)
_STORED_NAME = re.compile(r"^[0-9a-f]{32}(?:\.[a-z0-9]{1,10})?$")


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
    extension = _extension(file)
    if extension not in TEXT_EXTENSIONS:
        raise HTTPException(
            status_code=415, detail="Upload a TXT, Markdown, PDF, or DOCX document."
        )
    content = await _read_limited(file, settings.MAX_UPLOAD_BYTES)
    if extension in {".md", ".txt"}:
        try:
            return {"text": content.decode("utf-8")}
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Text files must use UTF-8 encoding."
            ) from exc
    try:
        if extension == ".pdf":
            import pdfplumber

            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        else:
            import docx

            text = "\n".join(
                item.text for item in docx.Document(io.BytesIO(content)).paragraphs
            )
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail="The document could not be read."
        ) from exc
    return {"text": text}


@router.post("/upload-media", status_code=status.HTTP_201_CREATED)
async def upload_media(
    settings: SettingsDep,
    file: UploadFile = File(...),  # noqa: B008
) -> dict[str, str]:
    """Store accepted media and return an API-served URL for verification."""
    extension = _extension(file)
    if extension not in MEDIA_EXTENSIONS:
        raise HTTPException(
            status_code=415, detail="Upload a supported image, audio, or video file."
        )
    content = await _read_limited(file, settings.MAX_UPLOAD_BYTES)
    directory = Path(settings.UPLOAD_DIRECTORY).resolve()  # noqa: ASYNC240
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    (directory / stored_name).write_bytes(content)
    return {
        "url": (
            f"{settings.PUBLIC_API_URL.rstrip('/')}"
            f"{settings.API_V1_PREFIX}/files/media/{stored_name}"
        )
    }


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
