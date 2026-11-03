# backend/app/modules/admin/models/content_report.py

"""ORM-модель жалобы на контент."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (DateTime, ForeignKey, Integer, String, Text, inspect, text)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class ContentReport(Base):
	"""Жалоба с раздельными ссылками на автора и владельца контента."""

	__tablename__ = "content_reports"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	reporter_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	target_table: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
	)
	target_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		nullable=False,
		index=True,
	)
	target_owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	reason: Mapped[str] = mapped_column(
		String(100),
		nullable=False,
	)
	description: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	moderator_note: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	status: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default="new",
	)
	severity_score: Mapped[int] = mapped_column(
		Integer,
		default=1,
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

	reporter: Mapped["User | None"] = relationship(
		"User",
		back_populates="content_reports",
		foreign_keys=[reporter_id],
	)
	target_owner: Mapped["User | None"] = relationship(
		"User",
		foreign_keys=[target_owner_id],
	)

	def __repr__(self) -> str:
		"""Представление без текста жалобы и загрузки атрибутов."""
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<ContentReport(id={identifier!r})>"