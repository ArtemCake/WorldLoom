# backend/app/modules/auth/models/oauth.py

"""ORM-модель привязанного внешнего провайдера авторизации."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (DateTime, ForeignKey, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class OAuthProvider(Base):
	"""Связь пользователя с внешним провайдером."""

	__tablename__ = "user_providers"
	__table_args__ = (
		UniqueConstraint(
			"provider",
			"external_id",
			name="uq_provider_external_id",
		),
	)

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
	provider: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
	)
	external_id: Mapped[str] = mapped_column(
		String(255),
		nullable=False,
	)
	access_token: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	refresh_token: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	expires_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		nullable=True,
	)

	user: Mapped["User"] = relationship(
		"User",
		back_populates="oauth_providers",
	)