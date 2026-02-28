import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import relationship

from app.model.base import Base


class JobStatus(enum.StrEnum):
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


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    repo_url = Column(String(500), nullable=False)
    branch = Column(String(200), nullable=False, default="main")
    instruction = Column(Text, nullable=False)
    before_screenshot_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    k8s_job_name = Column(String(200), nullable=True)
    parent_job_id = Column(Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    parent_proposal_index = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    proposals: list["Proposal"] = relationship(
        "Proposal", back_populates="job", cascade="all, delete-orphan"
    )


class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    proposal_index = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    concept = Column(Text, nullable=False)
    plan = Column(Text, nullable=False)  # JSON array stored as text
    files = Column(Text, nullable=True)  # JSON array stored as text
    complexity = Column(String(20), nullable=True)
    status = Column(Enum(ProposalStatus), nullable=False, default=ProposalStatus.PENDING)
    after_screenshot_path = Column(String(500), nullable=True)
    diff_path = Column(Text, nullable=True)
    pr_url = Column(String(500), nullable=True)
    pr_status = Column(String(20), nullable=True)  # creating, created, failed
    k8s_job_name = Column(String(200), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    job: "Job" = relationship("Job", back_populates="proposals")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
