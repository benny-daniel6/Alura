import asyncio
import mimetypes
from pathlib import Path
from typing import Optional

import aiofiles

from app.core.config import settings

LOCAL_STORAGE_DIR = Path("data/storage")
LOCAL_STATIC_PREFIX = "/static/"


class StorageService:
    """
    Stores binary assets (originals, cutouts, thumbnails, outfit previews).

    - ENVIRONMENT=development: local disk under data/storage, served at /static/.
    - Any other environment: S3-compatible object storage only. Local disk is never
      read or written, and a missing S3 configuration raises instead of falling back.
    """

    def __init__(self, local_dir: Path = LOCAL_STORAGE_DIR):
        self.local_dir = local_dir
        self._s3_client = None

    @property
    def uses_local_storage(self) -> bool:
        return settings.ENVIRONMENT == "development"

    # ---------- S3 helpers ----------

    def _s3(self):
        if not (settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY):
            raise RuntimeError(
                "Local storage fallback is strictly disabled in production. Valid S3 configuration is required "
                "(S3_BUCKET_NAME, S3_ACCESS_KEY, S3_SECRET_KEY)."
            )
        if self._s3_client is None:
            import boto3
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
            )
        return self._s3_client

    def _public_base_url(self) -> str:
        if settings.S3_PUBLIC_BASE_URL:
            return settings.S3_PUBLIC_BASE_URL.rstrip("/")
        if settings.S3_ENDPOINT_URL:
            return f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET_NAME}"
        return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.S3_REGION}.amazonaws.com"

    def _key_from_url(self, url: str) -> str:
        if url.startswith(LOCAL_STATIC_PREFIX):
            raise RuntimeError(f"Refusing to resolve local storage path '{url}' outside development.")
        base = self._public_base_url() + "/"
        if url.startswith(base):
            return url[len(base):]
        return url.lstrip("/")

    # ---------- Local helpers ----------

    def _local_path(self, url: str) -> Path:
        clean_path = url.replace(LOCAL_STATIC_PREFIX, "", 1).lstrip("/")
        file_path = (self.local_dir / clean_path).resolve()
        if self.local_dir.resolve() not in file_path.parents:
            raise ValueError(f"Invalid storage path: {url}")
        return file_path

    # ---------- Public API ----------

    async def save_file(self, file_bytes: bytes, filename: str, subfolder: str = "originals") -> str:
        """Saves bytes and returns the URL clients should use to fetch them."""
        if not self.uses_local_storage:
            key = f"{subfolder}/{filename}"
            content_type: Optional[str] = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            client = self._s3()
            await asyncio.to_thread(
                client.put_object,
                Bucket=settings.S3_BUCKET_NAME,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
            return f"{self._public_base_url()}/{key}"

        folder_path = self.local_dir / subfolder
        folder_path.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(folder_path / filename, "wb") as f:
            await f.write(file_bytes)
        return f"{LOCAL_STATIC_PREFIX}{subfolder}/{filename}"

    async def read_file(self, url: str) -> bytes:
        if not self.uses_local_storage:
            client = self._s3()
            obj = await asyncio.to_thread(
                client.get_object, Bucket=settings.S3_BUCKET_NAME, Key=self._key_from_url(url)
            )
            return await asyncio.to_thread(obj["Body"].read)

        file_path = self._local_path(url)
        if not file_path.exists():
            raise FileNotFoundError(f"Stored file not found: {file_path}")
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def delete_file(self, url: str) -> bool:
        if not self.uses_local_storage:
            client = self._s3()
            await asyncio.to_thread(
                client.delete_object, Bucket=settings.S3_BUCKET_NAME, Key=self._key_from_url(url)
            )
            return True

        file_path = self._local_path(url)
        if file_path.exists():
            file_path.unlink()
            return True
        return False


storage_service = StorageService()
