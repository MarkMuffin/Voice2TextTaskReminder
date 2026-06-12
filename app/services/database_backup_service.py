import asyncio
import hashlib
import logging
import sqlite3
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.config import Settings

logger = logging.getLogger(__name__)


class S3Client(Protocol):
    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        **kwargs: object,
    ) -> None: ...

    def head_object(self, **kwargs: object) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class DatabaseBackupConfig:
    enabled: bool
    sqlite_path: Path | None
    endpoint_url: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    prefix: str = "db-backups"
    region: str = "auto"

    @classmethod
    def from_settings(cls, cfg: Settings) -> "DatabaseBackupConfig":
        return cls(
            enabled=cfg.enable_db_backup_to_r2,
            sqlite_path=_sqlite_path_from_database_url(cfg.database_url),
            endpoint_url=cfg.db_backup_r2_endpoint_url,
            bucket=cfg.db_backup_r2_bucket,
            access_key_id=cfg.db_backup_r2_access_key_id,
            secret_access_key=cfg.db_backup_r2_secret_access_key,
            prefix=cfg.db_backup_r2_prefix,
            region=cfg.db_backup_r2_region,
        )

    def disabled_reason(self) -> str | None:
        if not self.enabled:
            return "database backup to R2 is disabled"
        if self.sqlite_path is None:
            return "DATABASE_URL is not a file-backed SQLite database"
        missing = [
            name
            for name, value in (
                ("DB_BACKUP_R2_ENDPOINT_URL", self.endpoint_url),
                ("DB_BACKUP_R2_BUCKET", self.bucket),
                ("DB_BACKUP_R2_ACCESS_KEY_ID", self.access_key_id),
                ("DB_BACKUP_R2_SECRET_ACCESS_KEY", self.secret_access_key),
            )
            if not value
        ]
        if missing:
            return f"missing R2 backup settings: {', '.join(missing)}"
        if not self.sqlite_path.exists():
            return f"SQLite database file does not exist: {self.sqlite_path}"
        return None


@dataclass(frozen=True)
class DatabaseBackupResult:
    bucket: str
    latest_key: str
    snapshot_key: str
    size_bytes: int


class DatabaseBackupService:
    def __init__(
        self,
        config: DatabaseBackupConfig,
        s3_client: S3Client | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._s3_client = s3_client
        self._now = now or (lambda: datetime.now(UTC))

    async def backup_once(self) -> DatabaseBackupResult | None:
        return await asyncio.to_thread(self._backup_once_sync)

    def _backup_once_sync(self) -> DatabaseBackupResult | None:
        disabled_reason = self._config.disabled_reason()
        if disabled_reason:
            if self._config.enabled:
                logger.warning("Skipping database backup: %s", disabled_reason)
            else:
                logger.info("Skipping database backup: %s", disabled_reason)
            return None

        assert self._config.sqlite_path is not None
        sqlite_path = self._config.sqlite_path
        timestamp = _as_utc(self._now()).strftime("%Y%m%dT%H%M%SZ")

        with tempfile.TemporaryDirectory(prefix="voice2text-db-backup-") as temp_dir:
            snapshot_path = Path(temp_dir) / sqlite_path.name
            _create_sqlite_snapshot(sqlite_path, snapshot_path)

            size_bytes = snapshot_path.stat().st_size
            checksum_sha256 = _sha256_file(snapshot_path)
            latest_key = _object_key(self._config.prefix, "latest", sqlite_path.name)
            snapshot_key = _object_key(
                self._config.prefix, "snapshots", f"{timestamp}-{sqlite_path.name}"
            )
            client = self._s3_client or _build_r2_client(self._config)
            latest_checksum = _latest_backup_checksum(client, self._config.bucket, latest_key)
            if latest_checksum == checksum_sha256:
                logger.info(
                    "Skipping database backup: SQLite snapshot unchanged "
                    "(bucket=%s latest_key=%s checksum_sha256=%s)",
                    self._config.bucket,
                    latest_key,
                    checksum_sha256,
                )
                return None

            self._upload_snapshot(
                client, snapshot_path, latest_key, snapshot_key, timestamp, checksum_sha256
            )

        return DatabaseBackupResult(
            bucket=self._config.bucket,
            latest_key=latest_key,
            snapshot_key=snapshot_key,
            size_bytes=size_bytes,
        )

    def _upload_snapshot(
        self,
        client: S3Client,
        snapshot_path: Path,
        latest_key: str,
        snapshot_key: str,
        timestamp: str,
        checksum_sha256: str,
    ) -> None:
        extra_args: dict[str, str | dict[str, str]] = {
            "ContentType": "application/vnd.sqlite3",
            "Metadata": {
                "source": "voice2text-task-reminder",
                "created-at": timestamp,
                "sha256": checksum_sha256,
            },
        }
        client.upload_file(
            str(snapshot_path),
            self._config.bucket,
            snapshot_key,
            ExtraArgs=extra_args,
        )
        client.upload_file(
            str(snapshot_path),
            self._config.bucket,
            latest_key,
            ExtraArgs=extra_args,
        )
        logger.info(
            "Uploaded SQLite backup to R2 bucket=%s latest_key=%s snapshot_key=%s "
            "checksum_sha256=%s",
            self._config.bucket,
            latest_key,
            snapshot_key,
            checksum_sha256,
        )


def _sqlite_path_from_database_url(database_url: str) -> Path | None:
    try:
        url = make_url(database_url)
    except ArgumentError:
        return None

    if not url.drivername.startswith("sqlite"):
        return None
    if not url.database or url.database == ":memory:":
        return None
    return Path(url.database).expanduser()


def _create_sqlite_snapshot(source_path: Path, snapshot_path: Path) -> None:
    source_uri = source_path.resolve().as_uri() + "?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    try:
        snapshot = sqlite3.connect(snapshot_path)
        try:
            source.backup(snapshot)
        finally:
            snapshot.close()
    finally:
        source.close()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_backup_checksum(client: S3Client, bucket: str, latest_key: str) -> str | None:
    try:
        response = client.head_object(Bucket=bucket, Key=latest_key)
    except Exception as exc:
        if _is_missing_object_error(exc):
            return None
        raise

    metadata = response.get("Metadata")
    if not isinstance(metadata, Mapping):
        return None
    checksum = metadata.get("sha256")
    return checksum if isinstance(checksum, str) else None


def _is_missing_object_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return False
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return False
    code = error.get("Code")
    return str(code) in {"404", "NoSuchKey", "NotFound"}


def _object_key(prefix: str, *parts: str) -> str:
    clean_parts = [part.strip("/") for part in parts if part.strip("/")]
    clean_prefix = prefix.strip("/")
    if clean_prefix:
        clean_parts.insert(0, clean_prefix)
    return "/".join(clean_parts)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _build_r2_client(config: DatabaseBackupConfig) -> S3Client:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for database backup to R2. Install project dependencies first."
        ) from exc

    return cast(
        S3Client,
        boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name=config.region,
            config=Config(signature_version="s3v4"),
        ),
    )
