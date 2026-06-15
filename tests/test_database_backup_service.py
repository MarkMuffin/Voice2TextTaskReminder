import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.scheduler.scheduler import ReminderScheduler
from app.services.database_backup_service import (
    DatabaseBackupConfig,
    DatabaseBackupService,
)


class FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[dict[str, object]] = []
        self.objects: dict[str, dict[str, object]] = {}

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        **kwargs: object,
    ) -> None:
        assert Path(filename).exists()
        with sqlite3.connect(filename) as conn:
            title = conn.execute("select title from tasks").fetchone()[0]
        extra_args = kwargs.get("ExtraArgs")
        metadata: Mapping[str, str] = {}
        if isinstance(extra_args, Mapping):
            extra_metadata = extra_args.get("Metadata")
            if isinstance(extra_metadata, Mapping):
                metadata = {str(key): str(value) for key, value in extra_metadata.items()}
        self.objects[key] = {"bucket": bucket, "metadata": metadata}
        self.uploads.append(
            {
                "bucket": bucket,
                "key": key,
                "extra_args": extra_args,
                "metadata": metadata,
                "title": title,
            }
        )

    def head_object(self, **kwargs: object) -> Mapping[str, object]:
        key = str(kwargs["Key"])
        if key not in self.objects:
            raise FakeClientError("404")
        return {"Metadata": self.objects[key]["metadata"]}


def _create_sqlite_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("create table tasks (id integer primary key, title text not null)")
        conn.execute("insert into tasks (title) values (?)", ("Call mom",))


def test_config_from_settings_derives_file_backed_sqlite_path(tmp_path):
    db_path = tmp_path / "app.db"
    cfg = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        enable_db_backup_to_r2=True,
        db_backup_r2_endpoint_url="https://example.r2.cloudflarestorage.com",
        db_backup_r2_bucket="voice-bot",
        db_backup_r2_access_key_id="access-key",
        db_backup_r2_secret_access_key="secret-key",
    )

    backup_config = DatabaseBackupConfig.from_settings(cfg)

    assert backup_config.enabled is True
    assert backup_config.sqlite_path == db_path


def test_config_rejects_non_file_sqlite_database_url():
    cfg = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        enable_db_backup_to_r2=True,
        db_backup_r2_endpoint_url="https://example.r2.cloudflarestorage.com",
        db_backup_r2_bucket="voice-bot",
        db_backup_r2_access_key_id="access-key",
        db_backup_r2_secret_access_key="secret-key",
    )

    backup_config = DatabaseBackupConfig.from_settings(cfg)

    assert backup_config.sqlite_path is None
    assert backup_config.disabled_reason() == "DATABASE_URL is not a file-backed SQLite database"


def test_config_reports_missing_r2_settings(tmp_path):
    db_path = tmp_path / "app.db"
    _create_sqlite_db(db_path)
    backup_config = DatabaseBackupConfig(
        enabled=True,
        sqlite_path=db_path,
        endpoint_url="",
        bucket="voice-bot",
        access_key_id="",
        secret_access_key="secret-key",
    )

    reason = backup_config.disabled_reason()

    assert reason is not None
    assert "DB_BACKUP_R2_ENDPOINT_URL" in reason
    assert "DB_BACKUP_R2_ACCESS_KEY_ID" in reason


async def test_backup_once_uploads_timestamped_and_latest_sqlite_snapshots(tmp_path):
    db_path = tmp_path / "app.db"
    _create_sqlite_db(db_path)
    fake_s3 = FakeS3Client()
    backup_config = DatabaseBackupConfig(
        enabled=True,
        sqlite_path=db_path,
        endpoint_url="https://example.r2.cloudflarestorage.com",
        bucket="voice-bot",
        access_key_id="access-key",
        secret_access_key="secret-key",
        prefix="prod/backups",
    )
    service = DatabaseBackupService(
        backup_config,
        s3_client=fake_s3,
        now=lambda: datetime(2026, 6, 12, 10, 30, 45, tzinfo=UTC),
    )

    result = await service.backup_once()

    assert result is not None
    assert result.bucket == "voice-bot"
    assert result.latest_key == "prod/backups/latest/app.db"
    assert result.snapshot_key == "prod/backups/snapshots/20260612T103045Z-app.db"
    assert result.size_bytes > 0
    assert [upload["key"] for upload in fake_s3.uploads] == [
        "prod/backups/snapshots/20260612T103045Z-app.db",
        "prod/backups/latest/app.db",
    ]
    assert all(upload["metadata"]["sha256"] for upload in fake_s3.uploads)
    assert {upload["title"] for upload in fake_s3.uploads} == {"Call mom"}


async def test_backup_once_skips_upload_when_latest_checksum_matches(tmp_path, caplog):
    db_path = tmp_path / "app.db"
    _create_sqlite_db(db_path)
    fake_s3 = FakeS3Client()
    backup_config = DatabaseBackupConfig(
        enabled=True,
        sqlite_path=db_path,
        endpoint_url="https://example.r2.cloudflarestorage.com",
        bucket="voice-bot",
        access_key_id="access-key",
        secret_access_key="secret-key",
        prefix="prod/backups",
    )
    service = DatabaseBackupService(
        backup_config,
        s3_client=fake_s3,
        now=lambda: datetime(2026, 6, 12, 10, 30, 45, tzinfo=UTC),
    )

    first_result = await service.backup_once()
    fake_s3.uploads.clear()
    caplog.set_level("INFO")

    second_result = await service.backup_once()

    assert first_result is not None
    assert second_result is None
    assert fake_s3.uploads == []
    assert "Skipping database backup: SQLite snapshot unchanged" in caplog.text


async def test_backup_once_skips_when_disabled(tmp_path):
    db_path = tmp_path / "app.db"
    _create_sqlite_db(db_path)
    fake_s3 = FakeS3Client()
    backup_config = DatabaseBackupConfig(
        enabled=False,
        sqlite_path=db_path,
        endpoint_url="https://example.r2.cloudflarestorage.com",
        bucket="voice-bot",
        access_key_id="access-key",
        secret_access_key="secret-key",
    )
    service = DatabaseBackupService(backup_config, s3_client=fake_s3)

    result = await service.backup_once()

    assert result is None
    assert fake_s3.uploads == []


async def test_backup_once_warns_when_enabled_but_misconfigured(tmp_path, caplog):
    db_path = tmp_path / "app.db"
    _create_sqlite_db(db_path)
    fake_s3 = FakeS3Client()
    backup_config = DatabaseBackupConfig(
        enabled=True,
        sqlite_path=db_path,
        endpoint_url="",
        bucket="voice-bot",
        access_key_id="access-key",
        secret_access_key="secret-key",
    )
    service = DatabaseBackupService(backup_config, s3_client=fake_s3)
    caplog.set_level("WARNING")

    result = await service.backup_once()

    assert result is None
    assert fake_s3.uploads == []
    assert "Skipping database backup: missing R2 backup settings" in caplog.text


def test_scheduler_registers_database_backup_interval_job(tmp_path):
    db_path = tmp_path / "app.db"
    _create_sqlite_db(db_path)
    backup_config = DatabaseBackupConfig(
        enabled=True,
        sqlite_path=db_path,
        endpoint_url="https://example.r2.cloudflarestorage.com",
        bucket="voice-bot",
        access_key_id="access-key",
        secret_access_key="secret-key",
    )
    backup_service = DatabaseBackupService(backup_config, s3_client=FakeS3Client())
    scheduler = ReminderScheduler(container=object(), bot=object())

    scheduler.start_database_backup(backup_service, interval_seconds=3600)

    jobs = scheduler._scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "database_backup_to_r2"
    assert jobs[0].next_run_time is not None
