# backend/app/modules/catalog/models/skills.py

"""Справочники характеристик, навыков и переопределений их связи."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
	Boolean,
	DateTime,
	ForeignKey,
	String,
	Text,
	UniqueConstraint,
	inspect,
	text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str) -> str:
	"""Представление без чтения отношений и загрузки атрибутов."""
	state = inspect(instance)
	identifier = (
		state.identity[0]
		if state.identity is not None
		else state.dict.get("id")
	)
	return f"<{label}(id={identifier!r})>"


class Skill(Base):
	"""Навык с основной характеристикой."""

	__tablename__ = "skills"
	__table_args__ = (
		UniqueConstraint(
			"system_id", "slug", name="uq_skills_system_slug",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	name: Mapped[str] = mapped_column(String(50), nullable=False)
	slug: Mapped[str] = mapped_column(String(50), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	ability_score_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characteristics.id", ondelete="RESTRICT"),
		nullable=False,
		index=True,
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="skills",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_skills",
	)
	characteristic: Mapped["Characteristic"] = relationship(
		"Characteristic", back_populates="skills",
	)
	custom_characteristic_link: Mapped[
		"SkillCharacteristicMap | None"
	] = relationship(
		"SkillCharacteristicMap",
		uselist=False,
		back_populates="skill",
		cascade="all, delete-orphan",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Skill")


class Characteristic(Base):
	"""Базовая характеристика игровой системы."""

	__tablename__ = "characteristics"
	__table_args__ = (
		UniqueConstraint(
			"system_id",
			"abbreviation",
			name="uq_characteristics_system_abbr",
		),
		UniqueConstraint(
			"system_id",
			"full_name",
			name="uq_characteristics_system_name",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	abbreviation: Mapped[str] = mapped_column(String(3), nullable=False)
	full_name: Mapped[str] = mapped_column(String(50), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	is_active: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="characteristics",
	)
	skills: Mapped[list["Skill"]] = relationship(
		"Skill",
		back_populates="characteristic",
		cascade="all, delete-orphan",
	)
	sheets: Mapped[list["CharacterSheetAbilityScore"]] = relationship(
		"CharacterSheetAbilityScore",
		back_populates="characteristic",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	custom_skill_links: Mapped[list["SkillCharacteristicMap"]] = relationship(
		"SkillCharacteristicMap",
		back_populates="characteristic",
		cascade="all, delete-orphan",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Characteristic")


class SkillCharacteristicMap(Base):
	"""Сохранённое переопределение характеристики навыка."""

	__tablename__ = "skill_characteristic_map"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	skill_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("skills.id", ondelete="CASCADE"),
		nullable=False,
		unique=True,
	)
	characteristic_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characteristics.id", ondelete="RESTRICT"),
		nullable=False,
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship("GameSystem")
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="skill_char_maps",
	)
	skill: Mapped["Skill"] = relationship(
		"Skill", back_populates="custom_characteristic_link",
	)
	characteristic: Mapped["Characteristic"] = relationship(
		"Characteristic", back_populates="custom_skill_links",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="SkillCharacteristicMap")
