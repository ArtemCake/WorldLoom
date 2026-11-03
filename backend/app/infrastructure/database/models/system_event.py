# backend/app/infrastructure/database/models/system_event.py

"""ORM-модель технического события приложения."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, Integer, String, Text, inspect, text)
from sqlalchemy.dialects.postgresql import (JSONB, UUID as PG_UUID)
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.infrastructure.database.base import Base


class SystemEvent(Base):
	"""Техническое событие с прежними полями и значениями по умолчанию."""

	__tablename__ = "system_events"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	event_type: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
	)
	severity_level: Mapped[int] = mapped_column(
		Integer,
		default=2,
		nullable=False,
	)
	message: Mapped[str] = mapped_column(
		Text,
		nullable=False,
	)
	metadata_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	stacktrace: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	acknowledged: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)

	def __repr__(self) -> str:
		"""Представление без сообщения, трассировки и загрузки атрибутов."""
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<SystemEvent(id={identifier!r})>"