from typing import Generator

from sqlalchemy.orm import Session

from app.repository.database import SessionLocal
from app.repository.job_repository import JobRepository
from app.repository.proposal_repository import ProposalRepository
from app.repository.setting_repository import SettingRepository


class DIContainer:
    """依存性注入コンテナ"""

    @staticmethod
    def get_db() -> Generator[Session, None, None]:
        """データベースセッションを取得"""
        try:
            db = SessionLocal()
            yield db
        finally:
            db.close()

    @staticmethod
    def get_job_repository(db: Session) -> JobRepository:
        return JobRepository(db)

    @staticmethod
    def get_proposal_repository(db: Session) -> ProposalRepository:
        return ProposalRepository(db)

    @staticmethod
    def get_setting_repository(db: Session) -> SettingRepository:
        return SettingRepository(db)
