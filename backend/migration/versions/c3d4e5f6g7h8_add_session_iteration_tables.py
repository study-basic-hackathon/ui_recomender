"""add session and iteration tables, drop legacy job tables

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-02-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy tables and create sessions, iterations, proposals tables."""
    # Drop legacy tables (proposals has FK to jobs, drop first)
    op.drop_table("proposals")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS proposalstatus")
    op.execute("DROP TYPE IF EXISTS jobstatus")

    # Sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repo_url", sa.String(length=500), nullable=False),
        sa.Column("base_branch", sa.String(length=200), nullable=False, server_default="main"),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "archived", name="sessionstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Iterations table
    op.create_table(
        "iterations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("iteration_index", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("selected_proposal_index", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "analyzing",
                "analyzed",
                "implementing",
                "completed",
                "failed",
                name="iterationstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("before_screenshot_key", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("k8s_analyzer_job_name", sa.String(length=200), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "iteration_index", name="uq_iteration_session_index"
        ),
    )

    # Proposals table (linked to iterations)
    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("iteration_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("files", sa.Text(), nullable=True),
        sa.Column("complexity", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "implementing",
                "completed",
                "failed",
                name="proposalstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("after_screenshot_key", sa.String(length=500), nullable=True),
        sa.Column("diff_key", sa.Text(), nullable=True),
        sa.Column("pr_url", sa.String(length=500), nullable=True),
        sa.Column("pr_status", sa.String(length=20), nullable=True),
        sa.Column("k8s_job_name", sa.String(length=200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["iteration_id"], ["iterations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "iteration_id", "proposal_index", name="uq_proposal_iteration_index"
        ),
    )


def downgrade() -> None:
    """Drop new tables and recreate legacy tables."""
    op.drop_table("proposals")
    op.drop_table("iterations")
    op.drop_table("sessions")
    op.execute("DROP TYPE IF EXISTS proposalstatus")
    op.execute("DROP TYPE IF EXISTS iterationstatus")
    op.execute("DROP TYPE IF EXISTS sessionstatus")

    # Recreate legacy tables
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "analyzing", "analyzed", "implementing", "completed", "failed", name="jobstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("repo_url", sa.String(length=500), nullable=False),
        sa.Column("branch", sa.String(length=200), nullable=False, server_default="main"),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("before_screenshot_path", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("k8s_job_name", sa.String(length=200), nullable=True),
        sa.Column("parent_job_id", sa.Uuid(), nullable=True),
        sa.Column("parent_proposal_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("files", sa.Text(), nullable=True),
        sa.Column("complexity", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "implementing", "completed", "failed", name="proposalstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("after_screenshot_path", sa.String(length=500), nullable=True),
        sa.Column("diff_path", sa.Text(), nullable=True),
        sa.Column("pr_url", sa.String(length=500), nullable=True),
        sa.Column("pr_status", sa.String(length=20), nullable=True),
        sa.Column("k8s_job_name", sa.String(length=200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
