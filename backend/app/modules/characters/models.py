# backend/app/modules/characters/models.py

"""ORM-модели персонажей, игровых листов и их содержимого."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, inspect, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str, keys: tuple[str, ...] = ("id",)) -> str:
	"""Получить только несекретные ключи без загрузки атрибутов."""
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

class Character(Base):
	"""Глобальный шаблон персонажа, принадлежащий пользователю."""

	__tablename__ = "characters"

	__table_args__ = (
		CheckConstraint(
			"revision >= 1",
			name="ck_characters_revision_positive",
		),
		CheckConstraint(
			"""
			(
				state_json IS NULL
				AND state_rules_version_id IS NULL
			)
			OR
			(
				state_json IS NOT NULL
				AND state_rules_version_id IS NOT NULL
			)
			""",
			name="ck_characters_state_binding",
		),
		CheckConstraint(
			"""
			state_json IS NULL
			OR
			(
				jsonb_typeof(state_json) = 'object'
				AND state_json -> 'schema_version' = '1'::jsonb
				AND jsonb_typeof(
					state_json -> 'attributes'
				) = 'object'
			) IS TRUE
			""",
			name="ck_characters_state_shape",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	user_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	# Новый формат. SQL NULL означает отсутствие перенесённого состояния.
	state_json: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True),
		nullable=True,
	)
	state_rules_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey(
			"game_system_rules_versions.id",
			ondelete="RESTRICT",
		),
		nullable=True,
		index=True,
	)
	revision: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		default=1,
		server_default=text("1"),
	)
	level: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	hp_max: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	experience: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	race_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), ForeignKey("races.id"),
	)
	background_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), ForeignKey("backgrounds.id"),
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)
	owner: Mapped["User"] = relationship(
		"User", back_populates="created_characters",
	)
	sheets: Mapped[list["CharacterSheet"]] = relationship(
		"CharacterSheet",
		back_populates="base_character",
		cascade="save-update, merge",
		passive_deletes=True,
	)
	__mapper_args__ = {
		"version_id_col": revision,
	}

	def __repr__(self) -> str:
		return _identity_repr(self, label="Character")

class CharacterSheet(Base):
	"""Состояние персонажа внутри конкретной игры."""

	__tablename__ = "character_sheets"

	__table_args__ = (
		CheckConstraint(
			"revision >= 1",
			name="ck_character_sheets_revision_positive",
		),
		CheckConstraint(
			"""
			(
				state_json IS NULL
				AND state_rules_version_id IS NULL
			)
			OR
			(
				state_json IS NOT NULL
				AND state_rules_version_id IS NOT NULL
			)
			""",
			name="ck_character_sheets_state_binding",
		),
		CheckConstraint(
			"""
			state_json IS NULL
			OR
			(
				jsonb_typeof(state_json) = 'object'
				AND state_json -> 'schema_version' = '1'::jsonb
				AND jsonb_typeof(
					state_json -> 'attributes'
				) = 'object'
			) IS TRUE
			""",
			name="ck_character_sheets_state_shape",
		),
	)
	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	player_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	game_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("games.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	base_character_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characters.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	npc_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("npcs.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	party_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("party.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	version_note: Mapped[str | None] = mapped_column(Text, nullable=True)
	# Новый формат. До явного преобразования старой записи остаётся NULL.
	state_json: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True),
		nullable=True,
	)
	state_rules_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey(
			"game_system_rules_versions.id",
			ondelete="RESTRICT",
		),
		nullable=True,
		index=True,
	)
	revision: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		default=1,
		server_default=text("1"),
	)
	stats_json: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True),
		nullable=True,
	)
	saves_json: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True),
		nullable=True,
	)
	skills_json: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True),
		nullable=True,
	)
	spell_slots_json: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True),
		nullable=True,
	)

	hp_current: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	hp_temp: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	death_saves_success: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	death_saves_failure: Mapped[int | None] = mapped_column(
		Integer,
		nullable=True,
	)
	conditions_json: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True),
		nullable=True,
	)
	is_active_in_game: Mapped[bool] = mapped_column(
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
	player: Mapped["User"] = relationship("User")
	base_character: Mapped["Character | None"] = relationship(
		"Character",
		back_populates="sheets",
	)
	npc: Mapped["NPC | None"] = relationship("NPC")
	inventory: Mapped[list["CharacterInventory"]] = relationship(
		"CharacterInventory",
		back_populates="sheet",
		cascade="all, delete-orphan",
	)
	tokens: Mapped[list["Token"]] = relationship(
		"Token",
		back_populates="character_sheet",
		cascade="save-update, merge",
		passive_deletes=True,
	)
	ability_scores: Mapped[list["CharacterSheetAbilityScore"]] = relationship(
		"CharacterSheetAbilityScore",
		back_populates="sheet",
		cascade="all, delete-orphan",
	)
	party: Mapped["Party | None"] = relationship(
		"Party", back_populates="character_sheets",
	)
	game: Mapped["Game"] = relationship(
		"Game", back_populates="character_sheets",
	)
	spells: Mapped[list["CharacterSheetSpell"]] = relationship(
		"CharacterSheetSpell",
		back_populates="sheet",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	__mapper_args__ = {
		"version_id_col": revision,
	}

	def __repr__(self) -> str:
		return _identity_repr(self, label="CharacterSheet")

class CharacterInventory(Base):
	"""Предмет в листе персонажа с сохранением прежнего ключа."""

	__tablename__ = "character_inventory"

	sheet_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		primary_key=True,
	)
	item_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("equipment.id", ondelete="CASCADE"),
		primary_key=True,
	)
	quantity: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default="1",
	)
	is_attuned: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	is_equipped: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	equipped_slot: Mapped[str | None] = mapped_column(
		String(30), nullable=True,
	)
	ammo_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
	charges_current: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	custom_name: Mapped[str | None] = mapped_column(
		String(255), nullable=True,
	)
	notes_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)
	npc_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("npcs.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)

	owner_npc: Mapped["NPC | None"] = relationship(
		"NPC", back_populates="inventory",
	)
	sheet: Mapped["CharacterSheet"] = relationship(
		"CharacterSheet", back_populates="inventory",
	)
	item: Mapped["Equipment"] = relationship("Equipment")

	def __repr__(self) -> str:
		return _identity_repr(
			self,
			label="CharacterInventory",
			keys=("sheet_id", "item_id"),
		)

class CharacterSheetAbilityScore(Base):
	"""Значение характеристики в конкретном листе."""

	__tablename__ = "character_ability_scores"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	character_sheet_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	characteristic_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characteristics.id", ondelete="RESTRICT"),
		nullable=False,
		index=True,
	)
	value: Mapped[int] = mapped_column(Integer, nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	sheet: Mapped["CharacterSheet"] = relationship(
		"CharacterSheet", back_populates="ability_scores",
	)
	characteristic: Mapped["Characteristic"] = relationship(
		"Characteristic", back_populates="sheets",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="CharacterSheetAbilityScore")

class CharacterSheetSpell(Base):
	"""Известное и подготовленное заклинание в листе персонажа."""

	__tablename__ = "character_sheet_spells"
	__table_args__ = (
		UniqueConstraint(
			"sheet_id",
			"spell_id",
			name="uq_character_sheet_spells_sheet_spell",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	sheet_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	spell_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("spells.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	is_known: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	is_prepared: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)

	sheet: Mapped["CharacterSheet"] = relationship(
		"CharacterSheet", back_populates="spells",
	)
	spell: Mapped["Spell"] = relationship("Spell")

	def __repr__(self) -> str:
		return _identity_repr(self, label="CharacterSheetSpell")