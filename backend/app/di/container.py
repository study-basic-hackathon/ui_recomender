from collections.abc import Generator

from sqlalchemy.orm import Session

from app.repository.database import SessionLocal
from app.repository.setting_repository import SettingRepository
from app.service.log_stream_service import LogStreamService


class DIContainer:
    """依存性注入コンテナ"""

    _log_stream_service: LogStreamService | None = None

    @staticmethod
    def get_db() -> Generator[Session]:
        """データベースセッションを取得"""
        try:
            db = SessionLocal()
            yield db
        finally:
            db.close()

    @staticmethod
    def get_setting_repository(db: Session) -> SettingRepository:
        return SettingRepository(db)

    @classmethod
    def get_log_stream_service(cls) -> LogStreamService:
        if cls._log_stream_service is None:
            cls._log_stream_service = LogStreamService()
        return cls._log_stream_service
