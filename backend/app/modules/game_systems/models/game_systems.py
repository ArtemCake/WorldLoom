# backend/app/modules/game_systems/models/game_systems.py

"""ORM-модели игровых систем, домашних правил и версий правил."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, inspect, text)
from sqlalchemy.dialects.postgresql import (JSONB, UUID as PG_UUID)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str) -> str:
	"""Представление без загрузки атрибутов и содержимого правил."""
	state = inspect(instance)
	identifier = (
		state.identity[0]
		if state.identity is not None
		else state.dict.get("id")
	)
	return f"<{label}(id={identifier!r})>"

class GameSystem(Base):
	"""Карточка игровой системы и контейнер её справочников."""

	__tablename__ = "game_systems"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	name: Mapped[str] = mapped_column(
		String(100),
		unique=True,
		nullable=False,
	)
	slug: Mapped[str] = mapped_column(
		String(100),
		unique=True,
		nullable=False,
	)
	rules_engine_version: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default="1.0",
	)
	description: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
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

	races: Mapped[list["Race"]] = relationship(
		"Race", back_populates="system", cascade="all, delete-orphan",
	)
	classes: Mapped[list["CharacterClass"]] = relationship(
		"CharacterClass",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	spells: Mapped[list["Spell"]] = relationship(
		"Spell", back_populates="system", cascade="all, delete-orphan",
	)
	homebrew_rules: Mapped[list["HomebrewRule"]] = relationship(
		"HomebrewRule",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	backgrounds: Mapped[list["Background"]] = relationship(
		"Background",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	spell_levels: Mapped[list["SpellSlot"]] = relationship(
		"SpellSlot",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	magic_schools: Mapped[list["MagicSchool"]] = relationship(
		"MagicSchool",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	abilities: Mapped[list["Ability"]] = relationship(
		"Ability", back_populates="system", cascade="all, delete-orphan",
	)
	effects: Mapped[list["Effect"]] = relationship(
		"Effect", back_populates="system", cascade="all, delete-orphan",
	)
	damage_types: Mapped[list["DamageType"]] = relationship(
		"DamageType",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	skills: Mapped[list["Skill"]] = relationship(
		"Skill", back_populates="system", cascade="all, delete-orphan",
	)
	characteristics: Mapped[list["Characteristic"]] = relationship(
		"Characteristic",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	item_types: Mapped[list["ItemType"]] = relationship(
		"ItemType",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	rarities: Mapped[list["Rarity"]] = relationship(
		"Rarity", back_populates="system", cascade="all, delete-orphan",
	)
	weapon_types: Mapped[list["WeaponType"]] = relationship(
		"WeaponType",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	armor_types: Mapped[list["ArmorType"]] = relationship(
		"ArmorType",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	creature_sizes: Mapped[list["CreatureSize"]] = relationship(
		"CreatureSize",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	creature_types: Mapped[list["CreatureType"]] = relationship(
		"CreatureType",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	languages: Mapped[list["Language"]] = relationship(
		"Language",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	lore: Mapped[list["LoreEntry"]] = relationship(
		"LoreEntry",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	npc_types: Mapped[list["NPCTag"]] = relationship(
		"NPCTag", back_populates="system", cascade="all, delete-orphan",
	)
	bestiary: Mapped[list["Creature"]] = relationship(
		"Creature",
		back_populates="system",
		cascade="all, delete-orphan",
	)
	feats: Mapped[list["Feat"]] = relationship(
		"Feat",
		back_populates="system",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	origins: Mapped[list["Origin"]] = relationship(
		"Origin",
		back_populates="system",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	equipment: Mapped[list["Equipment"]] = relationship(
		"Equipment",
		back_populates="system",
		cascade="all, delete-orphan",
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystem")

class HomebrewRule(Base):
	"""Домашнее правило с необязательной ссылкой на владельца."""

	__tablename__ = "homebrew_rules"

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
	title: Mapped[str] = mapped_column(
		String(255),
		nullable=False,
	)
	json_body: Mapped[dict] = mapped_column(
		JSONB,
		nullable=False,
		server_default="{}",
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
		back_populates="homebrew_rules",
	)
	owner: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_homebrew_rules",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="HomebrewRule")

class GameSystemRulesDraft(Base):
	"""Редактируемый черновик с проверкой конкурентных изменений."""

	__tablename__ = "game_system_rules_drafts"

	__table_args__ = (
		UniqueConstraint(
			"system_id",
			name="uq_game_system_rules_drafts_system",
		),
		CheckConstraint(
			"revision >= 1",
			name="ck_game_system_rules_drafts_revision_positive",
		),
		CheckConstraint(
			"jsonb_typeof(rules_json) = 'object'",
			name="ck_game_system_rules_drafts_rules_object",
		),
		CheckConstraint(
			"""
			(
				engine_version_id IS NULL
				AND rules_overrides_json IS NULL
			)
			OR
			(
				engine_version_id IS NOT NULL
				AND rules_overrides_json IS NOT NULL
				AND jsonb_typeof(rules_overrides_json) = 'object'
			)
			""",
			name="ck_game_system_rules_drafts_engine_origin",
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
	)
	engine_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("rule_engine_versions.id", ondelete="RESTRICT"),
		nullable=True,
		index=True,
	)
	rules_overrides_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
	)
	rules_json: Mapped[dict] = mapped_column(
		JSONB,
		nullable=False,
	)
	revision: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		default=1,
		server_default=text("1"),
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
		onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship("GameSystem")

	__mapper_args__ = {
		"version_id_col": revision,
	}

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystemRulesDraft")

class GameSystemRulesVersion(Base):
	"""Опубликованный снимок конфигурации правил игровой системы."""

	__tablename__ = "game_system_rules_versions"

	__table_args__ = (
		UniqueConstraint(
			"system_id",
			"version_number",
			name="uq_game_system_rules_versions_number",
		),
		UniqueConstraint(
			"system_id",
			"id",
			name="uq_game_system_rules_versions_system_id",
		),
		CheckConstraint(
			"version_number >= 1",
			name="ck_game_system_rules_versions_number_positive",
		),
		CheckConstraint(
			"jsonb_typeof(rules_json) = 'object'",
			name="ck_game_system_rules_versions_rules_object",
		),
		CheckConstraint(
			"""
			(
				engine_version_id IS NULL
				AND rules_overrides_json IS NULL
			)
			OR
			(
				engine_version_id IS NOT NULL
				AND rules_overrides_json IS NOT NULL
				AND jsonb_typeof(rules_overrides_json) = 'object'
			)
			""",
			name="ck_game_system_rules_versions_engine_origin",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="RESTRICT"),
		nullable=False,
	)
	version_number: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
	)
	engine_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("rule_engine_versions.id", ondelete="RESTRICT"),
		nullable=True,
		index=True,
	)
	rules_overrides_json: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
	)
	rules_json: Mapped[dict] = mapped_column(
		JSONB,
		nullable=False,
	)
	rules_engine_version: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
	)
	published_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship("GameSystem")

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystemRulesVersion")