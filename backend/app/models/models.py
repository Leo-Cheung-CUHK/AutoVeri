import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=gen_uuid
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    github_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    gitlab_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=gen_uuid
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    git_provider: Mapped[str] = mapped_column(
        Enum("github", "gitlab", name="git_provider_enum"), nullable=False
    )
    sim_command: Mapped[str] = mapped_column(String(512), nullable=False, default="make sim")
    tb_folder_pattern: Mapped[str] = mapped_column(String(128), nullable=False, default="tb_")
    rtl_folder_pattern: Mapped[str] = mapped_column(String(128), nullable=False, default="rtl_")
    timeout_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    notification_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    webhook_secret: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="projects")
    runners: Mapped[list["Runner"]] = relationship("Runner", back_populates="project")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="project")


class Runner(Base):
    __tablename__ = "runners"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=gen_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(
        Enum("linux", "mac", name="runner_platform_enum"), nullable=False
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="runners")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="runner")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=gen_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    runner_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("runners.id", ondelete="SET NULL"), nullable=True
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    branch: Mapped[str] = mapped_column(String(512), nullable=False)
    git_diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(
            "queued",
            "running",
            "logs_uploaded",
            "analyzing",
            "completed",
            "failed",
            "timeout",
            name="job_status_enum",
        ),
        nullable=False,
        default="queued",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="jobs")
    runner: Mapped[Optional["Runner"]] = relationship("Runner", back_populates="jobs")
    iterations: Mapped[list["JobIteration"]] = relationship("JobIteration", back_populates="job")
    parsed_errors: Mapped[list["ParsedError"]] = relationship("ParsedError", back_populates="job")
    debug_result: Mapped[Optional["DebugResult"]] = relationship(
        "DebugResult", back_populates="job", uselist=False
    )


class JobIteration(Base):
    __tablename__ = "job_iterations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=gen_uuid
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    patch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    errors_before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    errors_after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_errors_introduced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcome: Mapped[Optional[str]] = mapped_column(
        Enum("success", "errors_remain", "timeout", name="iteration_outcome_enum"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship("Job", back_populates="iterations")
    parsed_errors: Mapped[list["ParsedError"]] = relationship(
        "ParsedError", back_populates="iteration"
    )

    __table_args__ = (
        UniqueConstraint("job_id", "iteration_number", name="uq_job_iteration"),
    )


class ParsedError(Base):
    __tablename__ = "parsed_errors"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=gen_uuid
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iteration_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("job_iterations.id", ondelete="SET NULL"), nullable=True
    )
    error_type: Mapped[str] = mapped_column(
        Enum("TB_ERROR", "RTL_ERROR", "FATAL", name="error_type_enum"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    line_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sim_time: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    test_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="parsed_errors")
    iteration: Mapped[Optional["JobIteration"]] = relationship(
        "JobIteration", back_populates="parsed_errors"
    )


class DebugResult(Base):
    __tablename__ = "debug_results"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=gen_uuid
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    fix_target: Mapped[Optional[str]] = mapped_column(
        Enum("TB_ERROR", "RTL_ERROR", name="fix_target_enum"), nullable=True
    )
    confidence: Mapped[str] = mapped_column(
        Enum("high", "medium", "low", name="confidence_enum"), nullable=False
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    patch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    job: Mapped["Job"] = relationship("Job", back_populates="debug_result")
