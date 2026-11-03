# backend/app/infrastructure/database/models/active_session_cache.py

"""ORM-модель сохранённого состояния активного подключения."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, ForeignKey, String, inspect, text)
from sqlalchemy.dialects.postgresql import (JSONB, UUID as PG_UUID)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class ActiveSessionCache(Base):
	"""Состояние подключения с сохранением существующих ограничений."""

	__tablename__ = "active_sessions_cache"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	user_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		unique=True,
		index=True,
	)
	socket_id: Mapped[str] = mapped_column(
		String(255),
		nullable=False,
		unique=True,
	)
	connection_info_json: Mapped[dict] = mapped_column(
		JSONB,
		nullable=False,
		server_default="{}",
	)
	last_heartbeat: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)
	is_online: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
		nullable=False,
	)
	current_game_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("games.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
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

	user: Mapped["User"] = relationship("User")
	game: Mapped["Game | None"] = relationship("Game")

	def __repr__(self) -> str:
		"""Представление без идентификатора сокета и загрузки атрибутов."""
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<ActiveSessionCache(id={identifier!r})>"