from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.model.session import Session, SessionStatus


class SessionRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, session: Session) -> Session:
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_by_id(self, session_id: UUID) -> Session | None:
        return self.db.query(Session).filter(Session.id == session_id).first()

    def update_status(
        self, session_id: UUID, status: SessionStatus
    ) -> Session | None:
        session = self.get_by_id(session_id)
        if session:
            session.status = status
            self.db.commit()
            self.db.refresh(session)
        return session

    def list_all(self) -> list[Session]:
        return self.db.query(Session).order_by(Session.created_at.desc()).all()
