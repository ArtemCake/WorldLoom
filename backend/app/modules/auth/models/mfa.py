# backend/app/modules/auth/models/mfa.py

"""ORM-модель устройства многофакторной аутентификации."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, ForeignKey, String, func)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class MFADevice(Base):
	"""Устройство MFA; формат поля secret здесь не изменяется."""

	__tablename__ = "mfa_devices"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	user_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	type: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
	)
	secret: Mapped[str] = mapped_column(
		String(255),
		nullable=False,
	)
	label: Mapped[str | None] = mapped_column(
		String(100),
		nullable=True,
	)
	is_backup: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
	)

	user: Mapped["User"] = relationship(
		"User",
		back_populates="mfa_devices",
	)