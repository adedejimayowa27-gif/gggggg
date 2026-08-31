"""
Shared FastAPI dependencies.

`get_current_user` is the single choke point for route protection: any
route that takes it as a dependency requires a valid bearer token and an
active user. Later steps (business routes, AI assistant, etc.) reuse this
same dependency rather than re-implementing auth checks.
"""
import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.business import Business
from app.models.chat_conversation import ChatConversation
from app.models.simulation import Simulation
from app.models.alert import Alert
from app.models.google_integration import GoogleIntegration
from app.models.branch import Branch
from app.models.team_member import ROLE_ORDER, TeamMember
from app.models.user import User

# tokenUrl is only used by the OpenAPI docs UI to know where to fetch a token from.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise UnauthorizedError("Not authenticated.")

    subject = decode_access_token(token)
    if not subject:
        raise UnauthorizedError("Invalid or expired token.")

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise UnauthorizedError("Invalid token subject.")

    user = db.get(User, user_id)
    if not user:
        raise UnauthorizedError("User not found.")
    if not user.is_active:
        raise UnauthorizedError("User account is inactive.")

    return user


def get_owned_business(
    business_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Business:
    """
    Fetch a business by ID, scoped to the current user.

    This is the single choke point for the "a user must never see another
    business's data" requirement -- every route nested under
    /businesses/{business_id}/... should depend on this rather than
    querying Business directly, so the ownership check can never be
    accidentally skipped.

    Batch 10.2: also allows an active TeamMember (any role) to pass --
    purely additive. The original owner_id check runs first and is
    completely unchanged, so nothing about who could already access a
    business changes; this only ever grants access to *additional*,
    explicitly-added team members. A business with no team_members rows
    at all (impossible after this batch's migration backfill, but true
    of any freshly-created business until its owner row is inserted at
    creation time) still works exactly as before via the first check.
    """
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise NotFoundError("Business not found.")

    if business.owner_id == current_user.id:
        return business

    is_active_team_member = (
        db.query(TeamMember)
        .filter(
            TeamMember.business_id == business_id,
            TeamMember.user_id == current_user.id,
            TeamMember.status == "active",
        )
        .first()
    )
    if is_active_team_member:
        return business

    # 404, not 403 -- deliberately doesn't confirm the business exists to
    # someone who isn't authorized to see it.
    raise NotFoundError("Business not found.")


def get_business_role(business_id: uuid.UUID, db: Session, current_user: User) -> str | None:
    """
    This user's role on this business, or None if they have no access at
    all. The business's own owner_id user is always "owner" even before
    any TeamMember row would technically resolve it (defensive
    consistency with get_owned_business, in case a row is ever missing).
    """
    business = db.query(Business).filter(Business.id == business_id).first()
    if business and business.owner_id == current_user.id:
        return "owner"

    member = (
        db.query(TeamMember)
        .filter(
            TeamMember.business_id == business_id,
            TeamMember.user_id == current_user.id,
            TeamMember.status == "active",
        )
        .first()
    )
    return member.role if member else None


def require_business_role(minimum_role: str):
    """
    Dependency factory: returns a FastAPI dependency that only allows the
    request through if the current user's role on this business meets or
    exceeds `minimum_role` (viewer < member < admin < owner). Use this
    instead of get_owned_business on a route that should be restricted
    beyond "any active team member" -- e.g.
    `business: Business = Depends(require_business_role("admin"))`.

    Raises the same NotFoundError (never a 403) as get_owned_business, for
    the same reason: a team member below the required role shouldn't be
    able to distinguish "you're not allowed" from "this doesn't exist".
    """

    def _dependency(
        business_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> Business:
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise NotFoundError("Business not found.")

        role = get_business_role(business_id, db, current_user)
        if role is None or ROLE_ORDER.get(role, -1) < ROLE_ORDER.get(minimum_role, 0):
            raise NotFoundError("Business not found.")
        return business

    return _dependency


def get_owned_conversation(
    conversation_id: uuid.UUID, business: Business, db: Session
) -> ChatConversation:
    """
    Fetch a chat conversation by ID, scoped to a given (already
    ownership-checked) business.

    Batch 6.7: previously defined identically in both app.api.routes.chat
    and app.api.routes.assistant.py -- consolidated here alongside
    get_owned_business so there is one place a conversation's business
    scoping is enforced, the same reasoning as get_owned_business above.
    Called directly (not via FastAPI's Depends) since callers already have
    `business` from their own get_owned_business dependency and only need
    this when a request also references a specific conversation_id.
    """
    conversation = (
        db.query(ChatConversation)
        .filter(
            ChatConversation.id == conversation_id,
            ChatConversation.business_id == business.id,
        )
        .first()
    )
    if not conversation:
        raise NotFoundError("Conversation not found.")
    return conversation


def get_owned_simulation(
    simulation_id: uuid.UUID, business: Business, db: Session
) -> Simulation:
    """Fetch a saved simulation scoped to an already-ownership-checked business."""
    simulation = (
        db.query(Simulation)
        .filter(Simulation.id == simulation_id, Simulation.business_id == business.id)
        .first()
    )
    if not simulation:
        raise NotFoundError("Simulation not found.")
    return simulation


def get_owned_alert(alert_id: uuid.UUID, business: Business, db: Session) -> Alert:
    """Fetch an alert scoped to an already-ownership-checked business."""
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.business_id == business.id).first()
    if not alert:
        raise NotFoundError("Alert not found.")
    return alert


def get_connected_google_integration(business: Business, db: Session) -> GoogleIntegration:
    """Fetch a business's connected Google account, or 404 if none is connected yet."""
    integration = db.query(GoogleIntegration).filter(GoogleIntegration.business_id == business.id).first()
    if not integration:
        raise NotFoundError("No Google account is connected for this business yet.")
    return integration


def get_owned_branch(branch_id: uuid.UUID, business: Business, db: Session) -> Branch:
    """Fetch a branch scoped to an already-ownership-checked business."""
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.business_id == business.id).first()
    if not branch:
        raise NotFoundError("Branch not found.")
    return branch


def get_owned_team_member(member_id: uuid.UUID, business: Business, db: Session) -> TeamMember:
    """Fetch a team member scoped to an already-ownership-checked business."""
    member = (
        db.query(TeamMember)
        .filter(TeamMember.id == member_id, TeamMember.business_id == business.id)
        .first()
    )
    if not member:
        raise NotFoundError("Team member not found.")
    return member
