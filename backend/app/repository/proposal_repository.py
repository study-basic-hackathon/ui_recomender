from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.model.session import Proposal, ProposalStatus


class ProposalRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def create(self, proposal: Proposal) -> Proposal:
        self.db.add(proposal)
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def get_by_id(self, proposal_id: UUID) -> Proposal | None:
        return self.db.query(Proposal).filter(Proposal.id == proposal_id).first()

    def get_by_iteration_and_index(
        self, iteration_id: UUID, proposal_index: int
    ) -> Proposal | None:
        return (
            self.db.query(Proposal)
            .filter(
                Proposal.iteration_id == iteration_id,
                Proposal.proposal_index == proposal_index,
            )
            .first()
        )

    def get_all_by_status(self, status: ProposalStatus) -> list[Proposal]:
        return self.db.query(Proposal).filter(Proposal.status == status).all()

    def get_all_for_iteration(self, iteration_id: UUID) -> list[Proposal]:
        return (
            self.db.query(Proposal)
            .filter(Proposal.iteration_id == iteration_id)
            .order_by(Proposal.proposal_index)
            .all()
        )

    def update_status_optimistic(
        self,
        proposal_id: UUID,
        expected_version: int,
        status: ProposalStatus,
        **kwargs: object,
    ) -> Proposal | None:
        """Update status with optimistic locking. Returns None if version mismatch."""
        rows = (
            self.db.query(Proposal)
            .filter(
                Proposal.id == proposal_id,
                Proposal.version == expected_version,
            )
            .update(
                {
                    "status": status,
                    "version": Proposal.version + 1,
                    **{k: v for k, v in kwargs.items() if hasattr(Proposal, k)},
                },
                synchronize_session="fetch",
            )
        )
        if rows == 0:
            self.db.rollback()
            return None
        self.db.commit()
        return self.get_by_id(proposal_id)
