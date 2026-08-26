"""
AI assistant route.

Nested under a specific business, same ownership pattern as chat.py --
the single route here depends on get_owned_business, so the assistant can
never be pointed at another business's data no matter what the request
body contains. Conversation/message storage itself (the ChatConversation
and ChatMessage models, and their plain CRUD routes) is Batch 5.2's
chat.py; this route reuses those models directly rather than duplicating
them, and only adds the LLM round trip in between saving the user's
message and saving the assistant's reply.
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.business import Business
from app.models.chat_conversation import ChatConversation
from app.models.chat_message import ChatMessage
from app.models.user import User
from app.schemas.assistant import AssistantMessageIn, AssistantMessageOut
from app.schemas.chat import ChatMessageOut
from app.services.ai_assistant import run_assistant

router = APIRouter(prefix="/businesses/{business_id}/assistant", tags=["assistant"])


def _get_owned_conversation(
    conversation_id: uuid.UUID, business: Business, db: Session
) -> ChatConversation:
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


@router.post("/messages", response_model=AssistantMessageOut, status_code=status.HTTP_201_CREATED)
def send_assistant_message(
    payload: AssistantMessageIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
    current_user: User = Depends(get_current_user),
):
    """
    Take one user message, run it (plus the conversation's prior history)
    through the tool-calling loop, and persist both the user message and
    the assistant's reply as ChatMessage rows.

    If conversation_id is omitted, a new conversation is started
    automatically, titled from the first message.
    """
    if payload.conversation_id is not None:
        conversation = _get_owned_conversation(payload.conversation_id, business, db)
    else:
        conversation = ChatConversation(
            business_id=business.id,
            user_id=current_user.id,
            title=payload.message.strip()[:255] or None,
        )
        db.add(conversation)

    # Assigning via the relationship (rather than a raw conversation_id)
    # lets SQLAlchemy order the inserts correctly even when `conversation`
    # is brand new and has no id yet.
    user_message = ChatMessage(role="user", content=payload.message, conversation=conversation)
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history_payload = [
        {"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")
    ]

    reply_text = run_assistant(db, business, history_payload)

    assistant_message = ChatMessage(
        conversation_id=conversation.id, role="assistant", content=reply_text
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return AssistantMessageOut(
        conversation_id=conversation.id,
        user_message=ChatMessageOut.model_validate(user_message),
        assistant_message=ChatMessageOut.model_validate(assistant_message),
    )
