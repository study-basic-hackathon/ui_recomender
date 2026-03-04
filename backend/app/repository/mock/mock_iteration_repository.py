from uuid import UUID

from app.model.session import Iteration, IterationStatus


class MockIterationRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Iteration] = {}

    def create(self, iteration: Iteration) -> Iteration:
        self._store[iteration.id] = iteration
        return iteration

    def get_by_id(self, iteration_id: UUID) -> Iteration | None:
        return self._store.get(iteration_id)

    def get_by_session_and_index(
        self, session_id: UUID, iteration_index: int
    ) -> Iteration | None:
        for it in self._store.values():
            if it.session_id == session_id and it.iteration_index == iteration_index:
                return it
        return None

    def get_latest_for_session(self, session_id: UUID) -> Iteration | None:
        iters = [it for it in self._store.values() if it.session_id == session_id]
        if not iters:
            return None
        return max(iters, key=lambda it: it.iteration_index)

    def get_all_for_session(self, session_id: UUID) -> list[Iteration]:
        return sorted(
            [it for it in self._store.values() if it.session_id == session_id],
            key=lambda it: it.iteration_index,
        )

    def update_status_optimistic(
        self,
        iteration_id: UUID,
        expected_version: int,
        status: IterationStatus,
        **kwargs: object,
    ) -> Iteration | None:
        iteration = self._store.get(iteration_id)
        if not iteration or iteration.version != expected_version:
            return None
        iteration.status = status
        iteration.version += 1
        for k, v in kwargs.items():
            if hasattr(iteration, k):
                setattr(iteration, k, v)
        return iteration

    def update_selected_proposal(
        self, iteration_id: UUID, proposal_index: int
    ) -> Iteration | None:
        iteration = self._store.get(iteration_id)
        if iteration:
            iteration.selected_proposal_index = proposal_index
        return iteration
