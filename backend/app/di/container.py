from collections.abc import Generator

from sqlalchemy.orm import Session

from app.repository.database import SessionLocal
from app.repository.setting_repository import SettingRepository


class DIContainer:
    """依存性注入コンテナ"""

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
