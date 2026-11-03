# backend/app/modules/media/models.py

"""Медиа-модели, перенесённые со старой декларативной основы."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text, inspect, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


class UploadedAsset(Base):
	__tablename__ = "uploaded_assets"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	uploader_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	equipment_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("equipment.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	campaign_map_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("campaign_maps.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	job_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("ai_generation_jobs.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)

	storage_path: Mapped[str] = mapped_column(
		String(1000), nullable=False,
	)
	original_filename: Mapped[str] = mapped_column(
		String(255), nullable=False,
	)
	mime_type: Mapped[str] = mapped_column(
		String(100), nullable=False,
	)
	file_size_bytes: Mapped[int] = mapped_column(
		Integer, nullable=False,
	)
	width_px: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	height_px: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	dpi: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	is_public: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	usage_rights: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		server_default="private",
	)
	ai_prompt: Mapped[str | None] = mapped_column(
		Text, nullable=True,
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

	uploader: Mapped["User"] = relationship(
		"User",
		back_populates="uploaded_assets",
	)
	map: Mapped["CampaignMap"] = relationship(
		"CampaignMap",
	)
	job: Mapped["AIGenerationJob | None"] = relationship(
		"AIGenerationJob",
		back_populates="target_asset",
		foreign_keys=[job_id],
	)
	equipment: Mapped["Equipment | None"] = relationship(
		"Equipment",
		back_populates="assets",
	)

	def __repr__(self) -> str:
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<UploadedAsset(id={identifier!r})>"

class AIGenerationJob(Base):
	__tablename__ = "ai_generation_jobs"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	owner_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	model_used: Mapped[str] = mapped_column(
		String(100), nullable=False,
	)
	prompt: Mapped[str] = mapped_column(
		Text, nullable=False,
	)
	negative_prompt: Mapped[str | None] = mapped_column(
		Text, nullable=True,
	)
	status: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default="pending",
	)
	priority: Mapped[int] = mapped_column(
		Integer, default=0, nullable=False,
	)
	cost_credits: Mapped[int] = mapped_column(
		Integer, default=0, nullable=False,
	)
	progress_percent: Mapped[int] = mapped_column(
		Integer, default=0, nullable=False,
	)
	result_metadata_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	error_log: Mapped[str | None] = mapped_column(
		Text, nullable=True,
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
	completed_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		nullable=True,
	)

	target_asset: Mapped["UploadedAsset | None"] = relationship(
		"UploadedAsset",
		back_populates="job",
		uselist=False,
		lazy="selectin",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_ai_jobs",
		foreign_keys=[owner_id],
		lazy="selectin",
	)

	def __repr__(self) -> str:
		state = inspect(self)
		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)
		return f"<AIGenerationJob(id={identifier!r})>"