# backend/app/modules/games/models/communication.py

"""ORM-модели чатов и сообщений игровой встречи."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, ForeignKey, String, Text, inspect, text)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class Chat(Base):
	"""Канал сообщений внутри игровой встречи."""

	__tablename__ = "chats"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	session_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("sessions.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	name: Mapped[str] = mapped_column(
		String(100),
		nullable=False,
	)
	chat_type: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
	)
	is_global: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
		nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	session: Mapped["Session"] = relationship(
		"Session",
		back_populates="chats",
	)
	messages: Mapped[list["Message"]] = relationship(
		"Message",
		back_populates="chat",
		cascade="all, delete-orphan",
	)

	def __repr__(self) -> str:
		"""Представление без загрузки ORM-атрибутов."""
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<Chat(id={identifier!r})>"

class Message(Base):
	"""Сообщение с необязательными ссылками на автора и бросок."""

	__tablename__ = "messages"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	chat_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("chats.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	sender_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	npc_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("npcs.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	content: Mapped[str] = mapped_column(
		Text,
		nullable=False,
	)
	dice_roll_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("dice_rolls.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	edited_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		nullable=True,
	)
	deleted_for_players: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)

	chat: Mapped["Chat"] = relationship(
		"Chat",
		back_populates="messages",
	)
	sender: Mapped["User | None"] = relationship(
		"User",
		back_populates="chat_messages",
	)
	npc: Mapped["NPC | None"] = relationship("NPC")
	dice_roll: Mapped["DiceRoll | None"] = relationship("DiceRoll")

	def __repr__(self) -> str:
		"""Представление без текста сообщения и загрузки атрибутов."""
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<Message(id={identifier!r})>"