from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
from typing import Iterator, Protocol

from ..config import Settings


class StorageError(RuntimeError):
    pass


class StorageBackend(Protocol):
    backend_name: str

    def stage_upload_file(
        self,
        *,
        workspace_id: str,
        job_id: str,
        extension: str,
        local_source_path: Path,
    ) -> str: ...

    def stage_output_file(
        self,
        *,
        workspace_id: str,
        job_id: str,
        local_source_path: Path,
    ) -> str: ...

    @contextmanager
    def materialize_input(self, reference: str) -> Iterator[Path]: ...

    def resolve_local_path(self, reference: str) -> Path | None: ...

    def generate_download_url(
        self,
        reference: str,
        *,
        download_name: str,
        expires_seconds: int,
    ) -> str | None: ...

    def delete_reference(self, reference: str) -> None: ...


class LocalStorageBackend:
    backend_name = "local"

    def __init__(self, *, input_dir: Path, output_dir: Path) -> None:
        self.input_dir = input_dir
        self.output_dir = output_dir

    def stage_upload_file(
        self,
        *,
        workspace_id: str,
        job_id: str,
        extension: str,
        local_source_path: Path,
    ) -> str:
        destination = self.input_dir / workspace_id / f"{job_id}{extension}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if local_source_path.resolve() != destination.resolve():
            shutil.copy2(local_source_path, destination)
            local_source_path.unlink(missing_ok=True)
        return str(destination)

    def stage_output_file(
        self,
        *,
        workspace_id: str,
        job_id: str,
        local_source_path: Path,
    ) -> str:
        destination = self.output_dir / workspace_id / f"{job_id}_fixed.pdf"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if local_source_path.resolve() != destination.resolve():
            shutil.copy2(local_source_path, destination)
            local_source_path.unlink(missing_ok=True)
        return str(destination)

    @contextmanager
    def materialize_input(self, reference: str) -> Iterator[Path]:
        path = Path(reference)
        if not path.exists():
            raise StorageError(f"Input file not found: {reference}")
        yield path

    def resolve_local_path(self, reference: str) -> Path | None:
        return Path(reference)

    def generate_download_url(
        self,
        reference: str,
        *,
        download_name: str,
        expires_seconds: int,
    ) -> str | None:
        del reference, download_name, expires_seconds
        return None

    def delete_reference(self, reference: str) -> None:
        Path(reference).unlink(missing_ok=True)


class S3StorageBackend:
    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        use_ssl: bool,
    ) -> None:
        if not bucket:
            raise StorageError("S3 backend requires PDF_SAAS_STORAGE_S3_BUCKET.")

        try:
            import boto3  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional runtime package.
            raise StorageError("S3 backend requires boto3 to be installed.") from exc

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            use_ssl=use_ssl,
        )

    def stage_upload_file(
        self,
        *,
        workspace_id: str,
        job_id: str,
        extension: str,
        local_source_path: Path,
    ) -> str:
        key = f"input/{workspace_id}/{job_id}{extension}"
        self._upload(local_source_path, key)
        return self._to_ref(key)

    def stage_output_file(
        self,
        *,
        workspace_id: str,
        job_id: str,
        local_source_path: Path,
    ) -> str:
        key = f"output/{workspace_id}/{job_id}_fixed.pdf"
        self._upload(local_source_path, key)
        return self._to_ref(key)

    @contextmanager
    def materialize_input(self, reference: str) -> Iterator[Path]:
        # Backward-compatibility for jobs created before S3 migration.
        if not reference.startswith("s3://"):
            local = Path(reference)
            if not local.exists():
                raise StorageError(f"Input file not found: {reference}")
            yield local
            return

        _, key = self._from_ref(reference)
        suffix = Path(key).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)

        try:
            self.client.download_file(self.bucket, key, str(temp_path))
            yield temp_path
        except Exception as exc:
            raise StorageError(f"Failed to materialize S3 input {reference}: {exc}") from exc
        finally:
            temp_path.unlink(missing_ok=True)

    def resolve_local_path(self, reference: str) -> Path | None:
        if reference.startswith("s3://"):
            return None
        return Path(reference)

    def generate_download_url(
        self,
        reference: str,
        *,
        download_name: str,
        expires_seconds: int,
    ) -> str | None:
        if not reference.startswith("s3://"):
            return None

        _, key = self._from_ref(reference)
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{download_name}"',
                },
                ExpiresIn=max(60, expires_seconds),
            )
        except Exception as exc:
            raise StorageError(f"Failed to create S3 download URL for {reference}: {exc}") from exc

    def delete_reference(self, reference: str) -> None:
        if not reference.startswith("s3://"):
            Path(reference).unlink(missing_ok=True)
            return
        _, key = self._from_ref(reference)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageError(f"Failed deleting S3 object {reference}: {exc}") from exc

    def _upload(self, local_source_path: Path, key: str) -> None:
        try:
            self.client.upload_file(str(local_source_path), self.bucket, key)
        except Exception as exc:
            raise StorageError(f"Failed uploading to S3 key {key}: {exc}") from exc
        finally:
            local_source_path.unlink(missing_ok=True)

    def _to_ref(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"

    def _from_ref(self, ref: str) -> tuple[str, str]:
        # ref format: s3://bucket/key...
        without_scheme = ref.removeprefix("s3://")
        if "/" not in without_scheme:
            raise StorageError(f"Invalid S3 reference format: {ref}")
        bucket, key = without_scheme.split("/", 1)
        if bucket != self.bucket:
            raise StorageError(f"S3 reference bucket mismatch: expected {self.bucket}, got {bucket}")
        if not key:
            raise StorageError(f"Invalid S3 reference key: {ref}")
        return bucket, key


def build_storage_backend(settings: Settings) -> StorageBackend:
    if settings.storage_backend == "s3":
        return S3StorageBackend(
            bucket=settings.storage_s3_bucket,
            region=settings.storage_s3_region,
            endpoint_url=settings.storage_s3_endpoint_url,
            access_key_id=settings.storage_s3_access_key_id,
            secret_access_key=settings.storage_s3_secret_access_key,
            use_ssl=settings.storage_s3_use_ssl,
        )

    return LocalStorageBackend(
        input_dir=settings.input_dir,
        output_dir=settings.output_dir,
    )
