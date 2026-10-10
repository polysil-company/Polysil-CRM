"""Shapes for /conversations and /staff-directory (FS-019), matching the frontend's
proposed contract."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from api.schemas.leads import UUID_RE

MESSAGE_MAX = 2000


class Person(BaseModel):
    id: str
    full_name: str
    role_name: str | None
    org_unit_name: str | None
    is_active: bool = Field(default=True, description="False for a colleague who has left: "
                            "the history stays readable, a new message is refused.")


class ResourceRef(BaseModel):
    type: str = Field(description="lead, in this version.")
    id: str
    label: str = Field(description="The inquiry number, filled by the backend.")


class Message(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    body: str
    resource: ResourceRef | None
    created_at: str


class Conversation(BaseModel):
    id: str
    participant: Person = Field(description="The other person. Conversations are one-to-one.")
    last_message: Message | None
    unread_count: int = Field(description="Their messages after you last read.")
    updated_at: str


class ConversationMeta(BaseModel):
    unread_total: int = Field(description="Across all your conversations, not only those listed.")


class ConversationList(BaseModel):
    data: list[Conversation]
    meta: ConversationMeta


class MessageMeta(BaseModel):
    next_cursor: str | None = Field(description="Loads older messages.")


class MessagePage(BaseModel):
    data: list[Message] = Field(description="Oldest first, so the thread reads top to bottom.")
    meta: MessageMeta


class StartConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: Annotated[str, Field(pattern=UUID_RE)]


class ResourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["lead"]
    id: Annotated[str, Field(pattern=UUID_RE)]


def _no_nul(v: str) -> str:
    # PostgreSQL text cannot hold NUL: a 500 in the INSERT otherwise (code review F-3)
    if "\x00" in v:
        raise ValueError("a message cannot contain a NUL character")
    return v


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                           max_length=MESSAGE_MAX), AfterValidator(_no_nul)]
    resource: ResourceIn | None = None


class MarkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    up_to: Annotated[str | None, Field(default=None, pattern=UUID_RE,
        description="The newest message your screen shows. Left out: everything so far.")]


class UnreadTotal(BaseModel):
    unread_total: int
