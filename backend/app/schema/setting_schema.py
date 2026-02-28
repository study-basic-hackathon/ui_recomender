from datetime import datetime

from pydantic import BaseModel


class SettingRequest(BaseModel):
    key: str
    value: str


class SettingResponse(BaseModel):
    key: str
    value: str
    updated_at: datetime | None = None
