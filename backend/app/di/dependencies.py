from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.di.container import DIContainer
from app.repository.setting_repository import SettingRepository
from app.service.log_stream_service import LogStreamService
from app.service.s3_service import S3Service


def get_db() -> Generator[Session]:
    """データベースセッションを取得"""
    yield from DIContainer.get_db()


def get_setting_repository(db: Session = Depends(get_db)) -> SettingRepository:
    return DIContainer.get_setting_repository(db)


def get_s3_service() -> S3Service:
    return S3Service()


def get_log_stream_service() -> LogStreamService:
    return DIContainer.get_log_stream_service()
