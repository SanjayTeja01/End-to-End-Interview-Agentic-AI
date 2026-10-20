"""Server-side file validation, storage and authorised access via short-lived presigned URLs."""
from __future__ import annotations

import hashlib
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO

from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.models import FileObject
from storage.minio.client import get_storage
from storage.minio.keys import key_institute

DOC_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
}
AUDIO_MIME = {"webm": "audio/webm", "wav": "audio/wav", "ogg": "audio/ogg", "mp4": "audio/mp4"}
VIDEO_MIME = {"webm": "video/webm", "mp4": "video/mp4"}


@dataclass
class ValidatedFile:
    data: bytes
    ext: str
    mime: str
    checksum: str
    size: int
    original_filename: str | None


def _sniff(data: bytes) -> str | None:
    """Detect type from content (magic bytes) — the client filename/MIME is never trusted."""
    try:
        import magic  # python-magic (libmagic)

        detected = magic.from_buffer(data[:8192], mime=True)
    except Exception:  # noqa: BLE001 — fall back to signatures below
        detected = None
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return None
        return None
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"OggS"):
        return "ogg"
    if data[4:8] == b"ftyp":
        return "mp4"
    if detected and detected.startswith("text/"):
        return "txt"
    try:
        data[:4096].decode("utf-8")
        return "txt"
    except UnicodeDecodeError:
        return None


def validate_upload(data: bytes, filename: str | None, *, allowed: dict[str, str], max_mb: int) -> ValidatedFile:
    if not data:
        raise ValidationFailed("Empty file")
    if len(data) > max_mb * 1024 * 1024:
        raise ValidationFailed(f"File exceeds {max_mb} MB limit")
    kind = _sniff(data)
    claimed = (filename or "").rsplit(".", 1)[-1].lower() if filename and "." in filename else None
    if kind == "txt" and claimed == "md":
        kind = "md"
    if kind not in allowed:
        raise ValidationFailed(f"Unsupported file type (allowed: {', '.join(sorted(allowed))})")
    safe_name = (filename or f"upload.{kind}").replace("/", "_").replace("\\", "_")[:255]
    return ValidatedFile(data=data, ext=kind, mime=allowed[kind], checksum=hashlib.sha256(data).hexdigest(),
                         size=len(data), original_filename=safe_name)


def store_file(db: Session, vf: ValidatedFile, *, key: str, owner_id: uuid.UUID | None, institute_id: uuid.UUID,
               file_type: str) -> FileObject:
    if key_institute(key) != str(institute_id):
        raise Forbidden("Object key does not match tenant")
    get_storage().put_bytes(key, vf.data, vf.mime)
    f = FileObject(owner_id=owner_id, institute_id=institute_id, object_key=key, original_filename=vf.original_filename,
                   mime_type=vf.mime, size=vf.size, checksum=vf.checksum, file_type=file_type)
    db.add(f)
    db.flush()
    return f


def store_generated(db: Session, data: bytes, *, key: str, mime: str, owner_id: uuid.UUID | None,
                    institute_id: uuid.UUID, file_type: str, filename: str | None = None) -> FileObject:
    vf = ValidatedFile(data=data, ext=key.rsplit(".", 1)[-1], mime=mime, checksum=hashlib.sha256(data).hexdigest(),
                       size=len(data), original_filename=filename)
    return store_file(db, vf, key=key, owner_id=owner_id, institute_id=institute_id, file_type=file_type)


def presigned_url_for(db: Session, file_id: uuid.UUID, user: CurrentUser, *, candidate_id: uuid.UUID | None = None) -> str:
    """Authorise first, then sign. `candidate_id` is the candidate the file belongs to (for student checks)."""
    f = db.get(FileObject, file_id)
    if f is None or f.deleted_at is not None or f.institute_id != user.institute_id:
        raise NotFound("File not found")
    if user.is_student:
        owner = candidate_id or f.owner_id
        if owner != user.id:
            raise NotFound("File not found")
    if key_institute(f.object_key) != str(user.institute_id):
        raise NotFound("File not found")
    return get_storage().presigned_get(f.object_key, expires_seconds=get_settings().presigned_url_expiry_seconds,
                                       filename=f.original_filename)
