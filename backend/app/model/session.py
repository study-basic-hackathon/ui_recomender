import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import relationship

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

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_url = Column(String(500), nullable=False)
    base_branch = Column(String(200), nullable=False, default="main")
    status = Column(Enum(SessionStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=SessionStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    iterations: list["Iteration"] = relationship(
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

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id = Column(Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    iteration_index = Column(Integer, nullable=False)
    instruction = Column(Text, nullable=False)
    selected_proposal_index = Column(Integer, nullable=True)
    status = Column(
        Enum(IterationStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=IterationStatus.PENDING
    )
    before_screenshot_key = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    k8s_analyzer_job_name = Column(String(200), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    session: "Session" = relationship("Session", back_populates="iterations")
    proposals: list["Proposal"] = relationship(
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

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    iteration_id = Column(
        Uuid, ForeignKey("iterations.id", ondelete="CASCADE"), nullable=False
    )
    proposal_index = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    concept = Column(Text, nullable=False)
    plan = Column(Text, nullable=False)
    files = Column(Text, nullable=True)
    complexity = Column(String(20), nullable=True)
    status = Column(
        Enum(ProposalStatus, name="proposalstatus", values_callable=lambda x: [e.value for e in x]), nullable=False, default=ProposalStatus.PENDING
    )
    after_screenshot_key = Column(String(500), nullable=True)
    diff_key = Column(Text, nullable=True)
    pr_url = Column(String(500), nullable=True)
    pr_status = Column(String(20), nullable=True)
    k8s_job_name = Column(String(200), nullable=True)
    error_message = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    iteration: "Iteration" = relationship("Iteration", back_populates="proposals")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
