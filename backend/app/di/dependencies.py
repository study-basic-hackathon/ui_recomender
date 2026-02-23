from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.di.container import DIContainer
from app.repository.job_repository import JobRepository
from app.repository.proposal_repository import ProposalRepository
from app.repository.setting_repository import SettingRepository
from app.service.artifact_service import ArtifactService


def get_db() -> Generator[Session]:
    """データベースセッションを取得"""
    yield from DIContainer.get_db()


def get_job_repository(db: Session = Depends(get_db)) -> JobRepository:
    return DIContainer.get_job_repository(db)


def get_proposal_repository(db: Session = Depends(get_db)) -> ProposalRepository:
    return DIContainer.get_proposal_repository(db)


def get_setting_repository(db: Session = Depends(get_db)) -> SettingRepository:
    return DIContainer.get_setting_repository(db)


def get_artifact_service() -> ArtifactService:
    return ArtifactService()
