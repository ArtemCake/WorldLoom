# backend/app/modules/admin/models/audit_log.py

"""ORM-модель журнала действий пользователей."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text, inspect, text)
from sqlalchemy.dialects.postgresql import (JSONB, UUID as PG_UUID)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class AuditLog(Base):
	"""Запись аудита с сохранением прежней структуры таблицы."""

	__tablename__ = "audit_logs"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	user_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	ip_address: Mapped[str | None] = mapped_column(
		String(45),
		nullable=True,
	)
	action_type: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
	)
	table_name: Mapped[str | None] = mapped_column(
		String(100),
		nullable=True,
	)
	record_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		nullable=True,
		index=True,
	)
	old_value_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
	)
	new_value_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
	)
	user_agent: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	severity_level: Mapped[int] = mapped_column(
		Integer,
		default=1,
		nullable=False,
	)
	is_read_by_admin: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)

	user: Mapped["User | None"] = relationship(
		"User",
		back_populates="audit_logs",
	)

	def __repr__(self) -> str:
		"""Представление без загрузки атрибутов и данных аудита."""
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<AuditLog(id={identifier!r})>"