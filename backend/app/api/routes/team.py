"""
Team member routes (Step 10, Batch 10.2, requirement #4).

Viewing the team requires only active membership (any role, via
get_owned_business); inviting, changing a role, or removing someone
requires "admin" or higher (via require_business_role) -- a plain
"member" or "viewer" can see who's on the team but can't change it.
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business, get_owned_team_member, require_business_role
from app.db.session import get_db
from app.models.business import Business
from app.models.team_member import TeamMember
from app.models.user import User
from app.schemas.team import TeamMemberInviteIn, TeamMemberOut, TeamMemberRoleUpdateIn
from app.services.team import invite_member, remove_member, update_member_role

router = APIRouter(prefix="/businesses/{business_id}/team", tags=["team"])


@router.get("", response_model=list[TeamMemberOut])
def list_team_members(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    members = (
        db.query(TeamMember)
        .filter(TeamMember.business_id == business.id)
        .order_by(TeamMember.created_at.asc())
        .all()
    )
    return [TeamMemberOut.model_validate(m) for m in members]


@router.post("", response_model=TeamMemberOut, status_code=status.HTTP_201_CREATED)
def invite_team_member(
    payload: TeamMemberInviteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    member = invite_member(db, business, current_user, payload.email, payload.role.value)
    return TeamMemberOut.model_validate(member)


@router.patch("/{member_id}", response_model=TeamMemberOut)
def update_team_member_role(
    member_id: uuid.UUID,
    payload: TeamMemberRoleUpdateIn,
    db: Session = Depends(get_db),
    business: Business = Depends(require_business_role("admin")),
):
    member = get_owned_team_member(member_id, business, db)
    updated = update_member_role(db, member, payload.role.value)
    return TeamMemberOut.model_validate(updated)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_team_member(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    business: Business = Depends(require_business_role("admin")),
):
    member = get_owned_team_member(member_id, business, db)
    remove_member(db, business, member)
