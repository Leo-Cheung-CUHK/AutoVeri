"""
Projects router — CRUD + Git webhook receiver.
"""

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Job, Project, User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    repo_url: str
    git_provider: str  # github | gitlab
    sim_command: str = "make sim"
    tb_folder_pattern: str = "tb_"
    rtl_folder_pattern: str = "rtl_"
    timeout_minutes: int = 30
    notification_email: Optional[EmailStr] = None

    @field_validator("git_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in ("github", "gitlab"):
            raise ValueError("git_provider must be 'github' or 'gitlab'")
        return v


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    repo_url: Optional[str] = None
    sim_command: Optional[str] = None
    tb_folder_pattern: Optional[str] = None
    rtl_folder_pattern: Optional[str] = None
    timeout_minutes: Optional[int] = None
    notification_email: Optional[EmailStr] = None


class ProjectOut(BaseModel):
    id: str
    user_id: str
    name: str
    repo_url: str
    git_provider: str
    sim_command: str
    tb_folder_pattern: str
    rtl_folder_pattern: str
    timeout_minutes: int
    notification_email: Optional[str]
    webhook_secret: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ProjectOut], summary="List user's projects")
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.user_id == current_user.id).order_by(Project.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="Create project")
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = Project(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=body.name,
        repo_url=body.repo_url,
        git_provider=body.git_provider,
        sim_command=body.sim_command,
        tb_folder_pattern=body.tb_folder_pattern,
        rtl_folder_pattern=body.rtl_folder_pattern,
        timeout_minutes=body.timeout_minutes,
        notification_email=body.notification_email,
        webhook_secret=secrets.token_hex(32),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut, summary="Get project details")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_owned_project(project_id, current_user.id, db)
    return project


@router.put("/{project_id}", response_model=ProjectOut, summary="Update project")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_owned_project(project_id, current_user.id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete project")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_owned_project(project_id, current_user.id, db)
    await db.delete(project)
    await db.commit()


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------

@router.post("/{project_id}/webhook", status_code=status.HTTP_202_ACCEPTED, summary="Receive Git webhook")
async def receive_webhook(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: Optional[str] = Header(None),
    x_gitlab_token: Optional[str] = Header(None),
):
    """
    Accept a push/PR webhook from GitHub or GitLab.
    Verifies HMAC signature, creates a queued Job.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    raw_body = await request.body()

    # Verify signature
    if project.git_provider == "github":
        _verify_github_signature(raw_body, project.webhook_secret, x_hub_signature_256)
    else:
        _verify_gitlab_token(project.webhook_secret, x_gitlab_token)

    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    # Extract commit info
    commit_sha, branch = _extract_push_info(payload, project.git_provider)
    if not commit_sha:
        # Not a push event we care about (e.g. ping); acknowledge silently
        return {"detail": "Event acknowledged, no job created"}

    # Compute timeout
    timeout_at = datetime.now(timezone.utc) + timedelta(minutes=project.timeout_minutes)

    job = Job(
        id=str(uuid.uuid4()),
        project_id=project.id,
        commit_sha=commit_sha,
        branch=branch,
        status="queued",
        timeout_at=timeout_at,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {"detail": "Job queued", "job_id": job.id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_project(project_id: str, user_id: str, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _verify_github_signature(body: bytes, secret: str, signature_header: Optional[str]) -> None:
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


def _verify_gitlab_token(secret: str, token_header: Optional[str]) -> None:
    if not token_header or not secrets.compare_digest(secret, token_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitLab webhook token",
        )


def _extract_push_info(payload: dict, git_provider: str) -> tuple[Optional[str], str]:
    """Return (commit_sha, branch) from webhook payload."""
    if git_provider == "github":
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
        after = payload.get("after")
        if after == "0000000000000000000000000000000000000000":
            return None, branch  # branch deleted
        return after, branch
    else:
        # GitLab push event
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
        commits = payload.get("commits", [])
        sha = commits[0]["id"] if commits else payload.get("checkout_sha")
        return sha, branch
