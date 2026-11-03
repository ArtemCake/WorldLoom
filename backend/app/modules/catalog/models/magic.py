# backend/app/modules/catalog/models/magic.py

"""Заклинания, магические ячейки, школы, способности и эффекты."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, inspect, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
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

class Spell(Base):
	"""Заклинание или заговор игровой системы."""

	__tablename__ = "spells"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
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
	higher_levels: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	level: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		server_default="0",
	)
	school_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("magic_schools.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	casting_time: Mapped[str] = mapped_column(
		String(100),
		nullable=False,
	)
	range: Mapped[str] = mapped_column(String(100), nullable=False)
	components: Mapped[dict] = mapped_column(
		JSONB,
		nullable=False,
		server_default=text(
			"'{\"v\": false, \"s\": false}'::jsonb"
		),
	)
	duration: Mapped[str] = mapped_column(String(100), nullable=False)
	is_ritual: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	requires_concentration: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	classes: Mapped[list[str] | None] = mapped_column(
		ARRAY(String),
		nullable=True,
	)
	subclasses: Mapped[list[UUID] | None] = mapped_column(
		ARRAY(PG_UUID(as_uuid=True)),
		nullable=True,
	)
	effect_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		server_default="private",
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
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

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		back_populates="spells",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_spells",
	)
	school: Mapped["MagicSchool | None"] = relationship(
		"MagicSchool",
		back_populates="spells",
	)
	damage_types: Mapped[list["DamageType"]] = relationship(
		"DamageType",
		secondary="spell_damage_types",
		back_populates="spells",
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Spell")

class SpellSlot(Base):
	"""Справочная запись уровня магической ячейки."""

	__tablename__ = "spell_levels"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
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
	level: Mapped[int] = mapped_column(Integer, nullable=False)
	name: Mapped[str] = mapped_column(String(50), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	base_slots_per_day: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		server_default="0",
	)
	min_spell_level_to_cast: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		server_default="0",
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		server_default="private",
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
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

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		back_populates="spell_levels",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_spell_levels",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="SpellSlot")

class MagicSchool(Base):
	"""Школа магии с описанием ограничений игрового мира."""

	__tablename__ = "magic_schools"
	__table_args__ = (
		UniqueConstraint(
			"system_id",
			"slug",
			name="uq_magic_schools_system_slug",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
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
	is_forbidden_in_setting: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	lore_restrictions: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	color_theme: Mapped[str | None] = mapped_column(
		String(7),
		nullable=True,
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		server_default="private",
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
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

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		back_populates="magic_schools",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_magic_schools",
	)
	spells: Mapped[list["Spell"]] = relationship(
		"Spell",
		back_populates="school",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="MagicSchool")

class Ability(Base):
	"""Классовая, расовая или иная справочная способность."""

	__tablename__ = "abilities"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
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
	activation_type: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
	)
	uses_per_day: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	recharge_condition: Mapped[str | None] = mapped_column(
		String(100),
		nullable=True,
	)
	prerequisites: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	effect_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		server_default="private",
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
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

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		back_populates="abilities",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_abilities",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Ability")

class Effect(Base):
	"""Переиспользуемое описание игрового эффекта."""

	__tablename__ = "effects"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
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
	effect_type: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
	)
	targets: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	value: Mapped[int | None] = mapped_column(Integer, nullable=True)
	dice_formula: Mapped[str | None] = mapped_column(
		String(20),
		nullable=True,
	)
	damage_type_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("damage_types.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	duration_type: Mapped[str | None] = mapped_column(
		String(50),
		nullable=True,
	)
	duration_value: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	concentration_required: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		server_default="private",
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
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

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		back_populates="effects",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_effects",
	)
	damage_type: Mapped["DamageType | None"] = relationship(
		"DamageType",
		back_populates="effects",
	)
	magical_items: Mapped[list["MagicalItem"]] = relationship(
		"MagicalItem",
		secondary="item_effects",
		back_populates="effects",
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Effect")

class DamageType(Base):
	"""Справочник типов урона."""

	__tablename__ = "damage_types"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
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
	name: Mapped[str] = mapped_column(
		String(50),
		unique=True,
		nullable=False,
	)
	slug: Mapped[str] = mapped_column(
		String(50),
		unique=True,
		nullable=False,
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	icon_url: Mapped[str | None] = mapped_column(
		String(500),
		nullable=True,
	)
	is_homebrew: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	visibility_scope: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		server_default="private",
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
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

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		back_populates="damage_types",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_damage_types",
	)

	effects: Mapped[list["Effect"]] = relationship(
		"Effect",
		back_populates="damage_type",
		cascade="save-update, merge",
		passive_deletes=True,
	)

	spells: Mapped[list["Spell"]] = relationship(
		"Spell",
		secondary="spell_damage_types",
		back_populates="damage_types",
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="DamageType")

class SpellDamageType(Base):
	"""Связь заклинания и типа наносимого урона."""

	__tablename__ = "spell_damage_types"

	spell_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("spells.id", ondelete="CASCADE"),
		primary_key=True,
	)
	damage_type_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("damage_types.id", ondelete="CASCADE"),
		primary_key=True,
	)

	def __repr__(self) -> str:
		return _identity_repr(
			self,
			label="SpellDamageType",
			keys=("spell_id", "damage_type_id"),
		)