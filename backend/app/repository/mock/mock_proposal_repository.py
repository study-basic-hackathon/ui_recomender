from uuid import UUID

from app.model.session import Proposal, ProposalStatus


class MockProposalRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Proposal] = {}

    def create(self, proposal: Proposal) -> Proposal:
        self._store[proposal.id] = proposal
        return proposal

    def get_by_id(self, proposal_id: UUID) -> Proposal | None:
        return self._store.get(proposal_id)

    def get_by_iteration_and_index(
        self, iteration_id: UUID, proposal_index: int
    ) -> Proposal | None:
        for p in self._store.values():
            if p.iteration_id == iteration_id and p.proposal_index == proposal_index:
                return p
        return None

    def get_all_by_status(self, status: ProposalStatus) -> list[Proposal]:
        return [p for p in self._store.values() if p.status == status]

    def get_all_for_iteration(self, iteration_id: UUID) -> list[Proposal]:
        return sorted(
            [p for p in self._store.values() if p.iteration_id == iteration_id],
            key=lambda p: p.proposal_index,
        )

    def update_status_optimistic(
        self,
        proposal_id: UUID,
        expected_version: int,
        status: ProposalStatus,
        **kwargs: object,
    ) -> Proposal | None:
        proposal = self._store.get(proposal_id)
        if not proposal or proposal.version != expected_version:
            return None
        proposal.status = status
        proposal.version += 1
        for k, v in kwargs.items():
            if hasattr(proposal, k):
                setattr(proposal, k, v)
        return proposal
