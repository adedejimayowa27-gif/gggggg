"""
Chat conversation/message storage routes.

Nested under a specific business (/businesses/{business_id}/conversations/...)
so every route inherits the ownership check from get_owned_business -- a
user can never reach another business's conversations, even by guessing an
ID. Conversation-scoped routes additionally re-check that the conversation
belongs to that business before touching its messages.

This batch only covers storage: create a conversation, list a business's
conversations, create a message, list a conversation's messages. The
actual AI completion call (sending messages to a model and storing the
reply) is out of scope here and lands in a later batch.
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business, get_owned_conversation
from app.db.session import get_db
from app.models.business import Business
from app.models.chat_conversation import ChatConversation
from app.models.chat_message import ChatMessage
from app.models.user import User
from app.schemas.chat import (
    ChatConversationCreate,
    ChatConversationOut,
    ChatMessageCreate,
    ChatMessageOut,
)

router = APIRouter(prefix="/businesses/{business_id}/conversations", tags=["chat"])


@router.post("", response_model=ChatConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ChatConversationCreate,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
    current_user: User = Depends(get_current_user),
):
    conversation = ChatConversation(
        business_id=business.id,
        user_id=current_user.id,
        title=payload.title,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ChatConversationOut.model_validate(conversation)


@router.get("", response_model=list[ChatConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    conversations = (
        db.query(ChatConversation)
        .filter(ChatConversation.business_id == business.id)
        .order_by(ChatConversation.created_at.desc())
        .all()
    )
    return [ChatConversationOut.model_validate(c) for c in conversations]


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    conversation_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    conversation = get_owned_conversation(conversation_id, business, db)

    message = ChatMessage(
        conversation_id=conversation.id,
        role=payload.role,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return ChatMessageOut.model_validate(message)


@router.get("/{conversation_id}/messages", response_model=list[ChatMessageOut])
def list_messages(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    conversation = get_owned_conversation(conversation_id, business, db)

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [ChatMessageOut.model_validate(m) for m in messages]
