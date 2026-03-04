from collections.abc import Generator

from sqlalchemy.orm import Session

from app.infra.log_stream_client import LogStreamClient
from app.repository.database import SessionLocal
from app.repository.setting_repository import SettingRepository


class DIContainer:
    """依存性注入コンテナ"""

    _log_stream_client: LogStreamClient | None = None

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
    def get_log_stream_client(cls) -> LogStreamClient:
        if cls._log_stream_client is None:
            cls._log_stream_client = LogStreamClient()
        return cls._log_stream_client
