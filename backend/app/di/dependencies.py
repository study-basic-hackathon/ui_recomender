from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.di.container import DIContainer
from app.infra.log_stream_client import LogStreamClient
from app.infra.s3_client import S3Client
from app.repository.setting_repository import SettingRepository


def get_db() -> Generator[Session]:
    """データベースセッションを取得"""
    yield from DIContainer.get_db()


def get_setting_repository(db: Session = Depends(get_db)) -> SettingRepository:
    return DIContainer.get_setting_repository(db)


def get_s3_client() -> S3Client:
    return S3Client()


def get_log_stream_client() -> LogStreamClient:
    return DIContainer.get_log_stream_client()
