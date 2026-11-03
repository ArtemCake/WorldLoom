# backend/app/modules/catalog/models/character_building.py

"""Справочники рас, классов, предысторий, черт и происхождений."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text, inspect, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str, keys: tuple[str, ...] = ("id",)) -> str:
	"""Представление без загрузки атрибутов и связанных объектов."""
	state = inspect(instance)
	values = (
		state.identity
		if state.identity is not None
		else tuple(state.dict.get(key) for key in keys)
	)
	fields = ", ".join(
		f"{key}={value!r}" for key, value in zip(keys, values)
	)
	return f"<{label}({fields})>"


# Типы столбцов выводятся из целевых столбцов после регистрации
# реальных таблиц races и languages — как в исходнике.
race_languages = Table(
	"race_languages",
	Base.metadata,
	Column("race_id", ForeignKey("races.id"), primary_key=True),
	Column("language_id", ForeignKey("languages.id"), primary_key=True),
)

class Race(Base):
	"""Справочная раса, принадлежащая игровой системе."""

	__tablename__ = "races"

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
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	size_id: Mapped[int | None] = mapped_column(
		Integer,
		ForeignKey("creature_sizes.id"),
		nullable=True,
	)
	speed: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default="30",
	)
	ability_bonuses: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	proficiencies: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50), nullable=False, server_default="private",
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

	languages: Mapped[list["Language"]] = relationship(
		"Language",
		back_populates="races",
		secondary="race_languages",
	)
	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="races",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_races",
	)
	size: Mapped["CreatureSize | None"] = relationship("CreatureSize")
	creature_types: Mapped[list["CreatureType"]] = relationship(
		"CreatureType",
		secondary="creature_type_race_link",
		back_populates="races",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Race")

class CharacterClass(Base):
	"""Справочный класс персонажа."""

	__tablename__ = "classes"

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
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	hit_die: Mapped[int] = mapped_column(Integer, nullable=False)
	spellcasting_ability: Mapped[str | None] = mapped_column(
		String(20), nullable=True,
	)
	starting_proficiencies: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	saving_throw_proficiencies: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50), nullable=False, server_default="private",
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
		"GameSystem", back_populates="classes",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_classes",
	)
	subclasses: Mapped[list["Subclass"]] = relationship(
		"Subclass",
		back_populates="parent_class",
		cascade="all, delete-orphan",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="CharacterClass")

class Subclass(Base):
	"""Специализация справочного класса."""

	__tablename__ = "subclasses"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	class_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("classes.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
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
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	level_unlock: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default="3",
	)
	features_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50), nullable=False, server_default="private",
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

	parent_class: Mapped["CharacterClass"] = relationship(
		"CharacterClass", back_populates="subclasses",
	)
	system: Mapped["GameSystem"] = relationship("GameSystem")
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_subclasses",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Subclass")

class Background(Base):
	"""Справочная предыстория персонажа."""

	__tablename__ = "backgrounds"

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
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	skill_proficiencies: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	tool_proficiencies: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	language_ids: Mapped[list[UUID] | None] = mapped_column(
		ARRAY(PG_UUID(as_uuid=True)), nullable=True,
	)
	feature_name: Mapped[str | None] = mapped_column(
		String(255), nullable=True,
	)
	feature_description: Mapped[str | None] = mapped_column(
		Text, nullable=True,
	)
	starting_equipment: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50), nullable=False, server_default="private",
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
		"GameSystem", back_populates="backgrounds",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_backgrounds",
	)
	languages: Mapped[list["Language"]] = relationship(
		"Language",
		secondary="background_languages",
		back_populates="backgrounds",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Background")

class BackgroundLanguage(Base):
	"""Связь предыстории и языка."""

	__tablename__ = "background_languages"

	background_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("backgrounds.id", ondelete="CASCADE"),
		primary_key=True,
	)
	language_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("languages.id", ondelete="CASCADE"),
		primary_key=True,
	)

	def __repr__(self) -> str:
		return _identity_repr(
			self,
			label="BackgroundLanguage",
			keys=("background_id", "language_id"),
		)

class Feat(Base):
	"""Справочная черта персонажа."""

	__tablename__ = "feats"

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
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	ability_increase: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True,
	)
	prerequisites: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50), nullable=False, server_default="private",
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
		"GameSystem", back_populates="feats",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_feats",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Feat")

class Origin(Base):
	"""Справочное происхождение; прежняя иерархия сохранена."""

	__tablename__ = "origins"

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
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	race_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("races.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	background_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("backgrounds.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	ability_bonuses: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	proficiencies: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	starting_equipment: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50), nullable=False, server_default="private",
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
	origin_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("origins.id", ondelete="CASCADE"),
		nullable=False,
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="origins",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_origins",
	)
	race: Mapped["Race | None"] = relationship("Race")
	background: Mapped["Background | None"] = relationship("Background")

	# Оба имени сохраняем для совместимости с исходным кодом.
	# Их использование проверим перед отдельным исправлением отношений.
	lang_objects: Mapped[list["Language"]] = relationship(
		"Language",
		secondary="origin_languages",
		back_populates="origins",
	)
	languages: Mapped[list["Language"]] = relationship(
		"Language",
		back_populates="origins",
		secondary="origin_languages",
		overlaps="lang_objects",
	)
	subraces: Mapped[list["Origin"]] = relationship(
		"Origin",
		backref=backref("parent_origin", remote_side=[id]),
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Origin")

class OriginLanguage(Base):
	"""Связь происхождения и языка."""

	__tablename__ = "origin_languages"

	origin_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("origins.id", ondelete="CASCADE"),
		primary_key=True,
	)
	language_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("languages.id", ondelete="CASCADE"),
		primary_key=True,
	)

	def __repr__(self) -> str:
		return _identity_repr(
			self,
			label="OriginLanguage",
			keys=("origin_id", "language_id"),
		)