import uuid
from datetime import datetime
from typing import Any

from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class OAuthAccountTable(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """fastapi-users OAuth accounts (table name `oauth_account`)."""


class UserTable(SQLAlchemyBaseUserTableUUID, Base):
    """fastapi-users users (table name `user`) plus profile columns."""

    display_name: Mapped[str] = mapped_column(
        String(120), nullable=False, server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    oauth_accounts: Mapped[list[OAuthAccountTable]] = relationship(lazy="joined")


class AccessTokenTable(SQLAlchemyBaseAccessTokenTableUUID, Base):
    """fastapi-users database sessions behind the `pharma_session` cookie."""

    __tablename__ = "access_tokens"


class ConversationTable(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_updated_id", "user_id", "updated_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    turn_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    summarized_turns: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MessageTable(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        Index(
            "ix_messages_conversation_created_id",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MessageCitationTable(Base):
    """A citation of an assistant message; chunk versions and releases are immutable corpus rows."""

    __tablename__ = "message_citations"
    __table_args__ = (
        CheckConstraint(
            "strategy IN ('search_only', 'chunk_window', 'full_section')",
            name="strategy",
        ),
        Index("ix_message_citations_chunk_version_id", "chunk_version_id"),
        Index("ix_message_citations_release_id", "release_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("corpus.chunk_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.releases.id", ondelete="RESTRICT"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    block_chunk_version_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False
    )


class FeedbackTable(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_feedback_user_message"),
    )

    feedback_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
