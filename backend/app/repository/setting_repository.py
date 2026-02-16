from typing import Optional

from sqlalchemy.orm import Session

from app.model.job import Setting


class SettingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_key(self, key: str) -> Optional[Setting]:
        return self.db.query(Setting).filter(Setting.key == key).first()

    def upsert(self, key: str, value: str) -> Setting:
        setting = self.get_by_key(key)
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            self.db.add(setting)
        self.db.commit()
        self.db.refresh(setting)
        return setting

    def list_all(self) -> list[Setting]:
        return self.db.query(Setting).order_by(Setting.key).all()

    def delete(self, key: str) -> bool:
        setting = self.get_by_key(key)
        if setting:
            self.db.delete(setting)
            self.db.commit()
            return True
        return False
