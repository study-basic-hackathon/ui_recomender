from uuid import UUID

from app.model.session import Session, SessionStatus


class MockSessionRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Session] = {}

    def create(self, session: Session) -> Session:
        self._store[session.id] = session
        return session

    def get_by_id(self, session_id: UUID) -> Session | None:
        return self._store.get(session_id)

    def update_status(self, session_id: UUID, status: SessionStatus) -> Session | None:
        session = self._store.get(session_id)
        if session:
            session.status = status
        return session

    def list_all(self) -> list[Session]:
        return list(self._store.values())
