# backend/app/modules/users/models/friendship.py

"""ORM-модель связи между пользователями."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, String, func)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class Friendship(Base):
	"""Направленная связь дружбы с прежним строковым статусом."""

	__tablename__ = "friends"
	__table_args__ = (
		CheckConstraint(
			"user_id != friend_user_id",
			name="ck_friendship_no_self",
		),
	)

	user_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		primary_key=True,
	)
	friend_user_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		primary_key=True,
	)
	status: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default="pending",
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
	)

	user: Mapped["User"] = relationship(
		"User",
		back_populates="friends_from",
		foreign_keys=[user_id],
	)
	friend: Mapped["User"] = relationship(
		"User",
		back_populates="friends_to",
		foreign_keys=[friend_user_id],
	)