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
    """
    business = (
        db.query(Business)
        .filter(Business.id == business_id, Business.owner_id == current_user.id)
        .first()
    )
    if not business:
        raise NotFoundError("Business not found.")
    return business


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
