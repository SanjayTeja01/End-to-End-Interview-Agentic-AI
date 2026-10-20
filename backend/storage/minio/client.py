"""MinIO client wrapper: private bucket management, upload, download, presigned URLs and deletion."""
from __future__ import annotations

import io
import logging
from datetime import timedelta
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable

log = logging.getLogger(__name__)


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def presigned_get(self, key: str, *, expires_seconds: int, filename: str | None = None) -> str: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def ping(self) -> bool: ...


class MinioStorage:
    def __init__(self) -> None:
        from minio import Minio  # imported lazily so pure modules/tests don't need it

        s = get_settings()
        self.bucket = s.minio_bucket
        secret = s.minio_secret_key.get_secret_value()
        self._client = Minio(s.minio_endpoint, access_key=s.minio_access_key, secret_key=secret, secure=s.minio_secure)
        # Presigned URLs are signed for the host the browser uses. A region is given so signing is offline.
        public = s.minio_public_endpoint or s.minio_endpoint
        self._signer = Minio(public, access_key=s.minio_access_key, secret_key=secret, secure=s.minio_secure,
                             region="us-east-1")

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)
            log.info("bucket_created", extra={"data": {"bucket": self.bucket}})
        # Buckets are private: explicitly remove any anonymous policy.
        try:
            self._client.delete_bucket_policy(self.bucket)
        except Exception:  # noqa: BLE001 — no policy set is fine
            pass

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(self.bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)
        except Exception as exc:  # noqa: BLE001
            raise ServiceUnavailable("Object storage unavailable") from exc

    def get_bytes(self, key: str) -> bytes:
        resp = self._client.get_object(self.bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def presigned_get(self, key: str, *, expires_seconds: int, filename: str | None = None) -> str:
        headers = {"response-content-disposition": f'inline; filename="{filename}"'} if filename else None
        return self._signer.presigned_get_object(self.bucket, key, expires=timedelta(seconds=expires_seconds),
                                                 response_headers=headers)

    def delete(self, key: str) -> None:
        self._client.remove_object(self.bucket, key)

    def exists(self, key: str) -> bool:
        try:
            self._client.stat_object(self.bucket, key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def ping(self) -> bool:
        try:
            return self._client.bucket_exists(self.bucket)
        except Exception:  # noqa: BLE001
            return False


class InMemoryStorage:
    """Test double with the same interface."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def ensure_bucket(self) -> None:
        return None

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key][0]

    def presigned_get(self, key: str, *, expires_seconds: int, filename: str | None = None) -> str:
        return f"memory://{key}?expires={expires_seconds}"

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.objects

    def ping(self) -> bool:
        return True


_override: ObjectStorage | None = None


def set_storage(storage: ObjectStorage | None) -> None:
    global _override
    _override = storage
    _default_storage.cache_clear()


@lru_cache
def _default_storage() -> ObjectStorage:
    return MinioStorage()


def get_storage() -> ObjectStorage:
    return _override or _default_storage()
