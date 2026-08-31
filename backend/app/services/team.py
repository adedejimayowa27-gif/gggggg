"""
Team membership service (Step 10, Batch 10.2, requirement #4).

Invite flow, deliberately simple since this app has no email-sending
infrastructure: inviting someone by email creates a TeamMember row
immediately. If a User with that email already exists, it's linked and
active right away. If not, it's stored "pending" with just the email --
whoever eventually signs up with that exact email gets automatically
linked and activated (see link_pending_invites, called from the signup
route). The business owner is expected to tell the invitee out-of-band
("hey, sign up with this email") since there's no invite email to send.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.models.business import Business
from app.models.team_member import ROLE_ORDER, TeamMember
from app.models.user import User

VALID_ROLES = set(ROLE_ORDER.keys())


def create_owner_membership(db: Session, business: Business, owner: User) -> TeamMember:
    """Called once, when a business is created -- gives the creator an explicit,
    queryable "owner" row instead of relying only on Business.owner_id."""
    member = TeamMember(
        id=uuid.uuid4(),
        business_id=business.id,
        user_id=owner.id,
        invited_email=owner.email,
        invited_by_user_id=owner.id,
        role="owner",
        status="active",
    )
    db.add(member)
    return member


def invite_member(db: Session, business: Business, invited_by: User, email: str, role: str) -> TeamMember:
    if role not in VALID_ROLES:
        raise ValidationError(f"role must be one of {sorted(VALID_ROLES)}.")
    if role == "owner":
        raise ValidationError("There can only be one owner -- invite as admin instead.")

    from app.services.billing import check_max_team_members  # local import avoids a circular import

    check_max_team_members(db, business)

    normalized_email = email.strip().lower()
    existing = (
        db.query(TeamMember)
        .filter(TeamMember.business_id == business.id, TeamMember.invited_email == normalized_email)
        .first()
    )
    if existing:
        raise ConflictError("This email has already been invited to this business.")

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    member = TeamMember(
        id=uuid.uuid4(),
        business_id=business.id,
        user_id=existing_user.id if existing_user else None,
        invited_email=normalized_email,
        invited_by_user_id=invited_by.id,
        role=role,
        status="active" if existing_user else "pending",
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def link_pending_invites(db: Session, user: User) -> None:
    """
    Called right after signup: activates any pending invite(s) that were
    made to this user's email before they had an account. Safe to call
    for every signup even when there are no pending invites (the common
    case) -- it's just a cheap, indexed lookup that finds nothing.
    """
    pending = (
        db.query(TeamMember)
        .filter(TeamMember.invited_email == user.email.strip().lower(), TeamMember.status == "pending")
        .all()
    )
    for member in pending:
        member.user_id = user.id
        member.status = "active"
    if pending:
        db.commit()


def remove_member(db: Session, business: Business, member: TeamMember) -> None:
    if member.role == "owner":
        raise ValidationError("The business owner can't be removed from their own business.")
    db.delete(member)
    db.commit()


def update_member_role(db: Session, member: TeamMember, new_role: str) -> TeamMember:
    if new_role not in VALID_ROLES:
        raise ValidationError(f"role must be one of {sorted(VALID_ROLES)}.")
    if member.role == "owner" or new_role == "owner":
        raise ValidationError("The owner role can't be changed or assigned this way.")
    member.role = new_role
    db.commit()
    db.refresh(member)
    return member


def get_user_businesses(db: Session, user: User) -> list[Business]:
    """
    Every business this user can access: ones they own, plus ones
    they're an active team member of. Used by list_businesses so a team
    member actually sees the businesses they've been added to (before
    this batch, that route only ever checked owner_id).
    """
    owned = db.query(Business).filter(Business.owner_id == user.id)
    member_business_ids = (
        db.query(TeamMember.business_id)
        .filter(TeamMember.user_id == user.id, TeamMember.status == "active")
        .scalar_subquery()
    )
    member_owned = db.query(Business).filter(Business.id.in_(member_business_ids))
    return owned.union(member_owned).order_by(Business.created_at.desc()).all()
