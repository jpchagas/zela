"""File storage behind a small interface: local disk for development, Cloud Storage in
production. Objects are addressed by opaque URIs stored on the owning row."""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class BlobStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes under `key` and return a URI for get()."""
        ...

    def get(self, uri: str) -> bytes: ...


class LocalBlobStore:
    def __init__(self, root: str):
        self._root = Path(root).resolve()

    def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"local://{key}"

    def get(self, uri: str) -> bytes:
        return self._path(uri.removeprefix("local://")).read_bytes()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root not in path.parents:
            raise ValueError("Storage key escapes the storage root")
        return path


class GCSBlobStore:
    def __init__(self, bucket: str):
        from google.cloud import storage  # optional dependency: '.[gcp]'

        self._bucket_name = bucket
        self._bucket = storage.Client().bucket(bucket)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self._bucket.blob(key).upload_from_string(data, content_type=content_type)
        return f"gs://{self._bucket_name}/{key}"

    def get(self, uri: str) -> bytes:
        key = uri.removeprefix(f"gs://{self._bucket_name}/")
        return self._bucket.blob(key).download_as_bytes()


@lru_cache
def get_blob_store() -> BlobStore:
    settings = get_settings()
    if settings.storage_backend == "gcs":
        return GCSBlobStore(settings.storage_bucket)
    return LocalBlobStore(settings.local_storage_dir)
