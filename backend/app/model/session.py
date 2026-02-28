import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.model.base import Base


class SessionStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class IterationStatus(enum.StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    IMPLEMENTING = "implementing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProposalStatus(enum.StrEnum):
    PENDING = "pending"
    IMPLEMENTING = "implementing"
    COMPLETED = "completed"
    FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_url: Mapped[str] = mapped_column(String(500))
    base_branch: Mapped[str] = mapped_column(String(200), default="main")
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, values_callable=lambda x: [e.value for e in x]),
        default=SessionStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    iterations: Mapped[list["Iteration"]] = relationship(
        "Iteration",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Iteration.iteration_index",
    )


class Iteration(Base):
    __tablename__ = "iterations"
    __table_args__ = (
        UniqueConstraint("session_id", "iteration_index", name="uq_iteration_session_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    iteration_index: Mapped[int] = mapped_column(Integer)
    instruction: Mapped[str] = mapped_column(Text)
    selected_proposal_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[IterationStatus] = mapped_column(
        Enum(IterationStatus, values_callable=lambda x: [e.value for e in x]),
        default=IterationStatus.PENDING,
    )
    before_screenshot_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    k8s_analyzer_job_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    session: Mapped["Session"] = relationship("Session", back_populates="iterations")
    proposals: Mapped[list["Proposal"]] = relationship(
        "Proposal",
        back_populates="iteration",
        cascade="all, delete-orphan",
        order_by="Proposal.proposal_index",
    )


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("iteration_id", "proposal_index", name="uq_proposal_iteration_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    iteration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("iterations.id", ondelete="CASCADE"),
    )
    proposal_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    concept: Mapped[str] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text)
    files: Mapped[str | None] = mapped_column(Text, nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(
            ProposalStatus,
            name="proposalstatus",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ProposalStatus.PENDING,
    )
    after_screenshot_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    diff_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pr_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    k8s_job_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    iteration: Mapped["Iteration"] = relationship("Iteration", back_populates="proposals")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
