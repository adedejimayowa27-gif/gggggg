"""
Pydantic schemas for the AI assistant endpoint.
"""
import uuid

from pydantic import BaseModel, Field

from app.schemas.chat import ChatMessageOut


class AssistantMessageIn(BaseModel):
    # Omit to start a new conversation; pass an existing conversation's id
    # to continue it (the route re-checks it belongs to this business).
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1)


class AssistantMessageOut(BaseModel):
    conversation_id: uuid.UUID
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
