"""Pydantic schemas for team membership (Step 10, requirement #4)."""
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TeamRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TeamMemberInviteIn(BaseModel):
    email: EmailStr
    role: TeamRole = TeamRole.MEMBER


class TeamMemberRoleUpdateIn(BaseModel):
    role: TeamRole


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    user_id: uuid.UUID | None
    invited_email: str
    role: TeamRole
    status: str
    created_at: datetime
