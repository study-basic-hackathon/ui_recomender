from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.di.dependencies import get_db
from app.repository.setting_repository import SettingRepository
from app.schema.job_schema import SettingRequest, SettingResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/", response_model=list[SettingResponse])
def get_settings(db: Session = Depends(get_db)) -> list[SettingResponse]:
    repo = SettingRepository(db)
    return [
        SettingResponse(key=s.key, value=s.value, updated_at=s.updated_at) for s in repo.list_all()
    ]


@router.post("/", response_model=SettingResponse)
def save_setting(request: SettingRequest, db: Session = Depends(get_db)) -> SettingResponse:
    repo = SettingRepository(db)
    setting = repo.upsert(request.key, request.value)
    return SettingResponse(key=setting.key, value=setting.value, updated_at=setting.updated_at)
