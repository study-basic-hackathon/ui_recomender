from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.model.job import Proposal, ProposalStatus


class ProposalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, proposal: Proposal) -> Proposal:
        self.db.add(proposal)
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def get_by_id(self, proposal_id: UUID) -> Optional[Proposal]:
        return self.db.query(Proposal).filter(Proposal.id == proposal_id).first()

    def get_by_job_and_index(
        self, job_id: UUID, proposal_index: int
    ) -> Optional[Proposal]:
        return (
            self.db.query(Proposal)
            .filter(
                Proposal.job_id == job_id,
                Proposal.proposal_index == proposal_index,
            )
            .first()
        )

    def get_all_for_job(self, job_id: UUID) -> list[Proposal]:
        return (
            self.db.query(Proposal)
            .filter(Proposal.job_id == job_id)
            .order_by(Proposal.proposal_index)
            .all()
        )

    def update_status(
        self, proposal_id: UUID, status: ProposalStatus, **kwargs: object
    ) -> Optional[Proposal]:
        proposal = self.get_by_id(proposal_id)
        if proposal:
            proposal.status = status
            for key, value in kwargs.items():
                if hasattr(proposal, key):
                    setattr(proposal, key, value)
            self.db.commit()
            self.db.refresh(proposal)
        return proposal
