from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.model.session import Iteration, IterationStatus


class IterationRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, iteration: Iteration) -> Iteration:
        self.db.add(iteration)
        self.db.commit()
        self.db.refresh(iteration)
        return iteration

    def get_by_id(self, iteration_id: UUID) -> Iteration | None:
        return self.db.query(Iteration).filter(Iteration.id == iteration_id).first()

    def get_by_session_and_index(
        self, session_id: UUID, iteration_index: int
    ) -> Iteration | None:
        return (
            self.db.query(Iteration)
            .filter(
                Iteration.session_id == session_id,
                Iteration.iteration_index == iteration_index,
            )
            .first()
        )

    def get_latest_for_session(self, session_id: UUID) -> Iteration | None:
        return (
            self.db.query(Iteration)
            .filter(Iteration.session_id == session_id)
            .order_by(Iteration.iteration_index.desc())
            .first()
        )

    def get_all_for_session(self, session_id: UUID) -> list[Iteration]:
        return (
            self.db.query(Iteration)
            .filter(Iteration.session_id == session_id)
            .order_by(Iteration.iteration_index)
            .all()
        )

    def update_status_optimistic(
        self,
        iteration_id: UUID,
        expected_version: int,
        status: IterationStatus,
        **kwargs: object,
    ) -> Iteration | None:
        """Update status with optimistic locking. Returns None if version mismatch."""
        rows = (
            self.db.query(Iteration)
            .filter(
                Iteration.id == iteration_id,
                Iteration.version == expected_version,
            )
            .update(
                {
                    "status": status,
                    "version": Iteration.version + 1,
                    **{k: v for k, v in kwargs.items() if hasattr(Iteration, k)},
                },
                synchronize_session="fetch",
            )
        )
        if rows == 0:
            self.db.rollback()
            return None
        self.db.commit()
        return self.get_by_id(iteration_id)

    def update_selected_proposal(
        self, iteration_id: UUID, proposal_index: int
    ) -> Iteration | None:
        iteration = self.get_by_id(iteration_id)
        if iteration:
            iteration.selected_proposal_index = proposal_index
            self.db.commit()
            self.db.refresh(iteration)
        return iteration
