# backend/app/modules/catalog/models/worldbuilding.py

"""Модели языков, бестиария, неигровых персонажей и лора."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint, inspect, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str, keys: tuple[str, ...] = ("id",)) -> str:
	"""Сформировать представление без загрузки атрибутов из БД."""
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

creature_type_race_link = Table(
	"creature_type_race_link",
	Base.metadata,
	Column(
		"creature_type_id",
		PG_UUID(as_uuid=True),
		ForeignKey("creature_types.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"race_id",
		PG_UUID(as_uuid=True),
		ForeignKey("races.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Index("ix_creature_type_race_type", "creature_type_id"),
	Index("ix_creature_type_race_race", "race_id"),
)

creature_npctag_link = Table(
	"creature_npctag_link",
	Base.metadata,
	Column(
		"creature_id",
		PG_UUID(as_uuid=True),
		ForeignKey("bestiary.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"npctag_id",
		PG_UUID(as_uuid=True),
		ForeignKey("npc_types.id", ondelete="CASCADE"),
		primary_key=True,
	),
)

creature_type_link = Table(
	"creature_type_link",
	Base.metadata,
	Column(
		"creature_id",
		PG_UUID(as_uuid=True),
		ForeignKey("bestiary.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"type_id",
		PG_UUID(as_uuid=True),
		ForeignKey("creature_types.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Index("ix_creature_type_creature", "creature_id"),
	Index("ix_creature_type_type", "type_id"),
)

npc_npctag_link = Table(
	"npc_npctag_link",
	Base.metadata,
	Column(
		"npc_id",
		PG_UUID(as_uuid=True),
		ForeignKey("npcs.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"npctag_id",
		PG_UUID(as_uuid=True),
		ForeignKey("npc_types.id", ondelete="CASCADE"),
		primary_key=True,
	),
)

class Language(Base):
	"""Язык игровой системы."""

	__tablename__ = "languages"
	__table_args__ = (
		UniqueConstraint(
			"system_id", "slug", name="uq_languages_system_slug",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	name: Mapped[str] = mapped_column(String(50), nullable=False)
	slug: Mapped[str] = mapped_column(String(50), nullable=False)
	script: Mapped[str | None] = mapped_column(String(50), nullable=True)
	is_standard: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	is_secret: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
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
		server_default=text("now()"), onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="languages",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_languages",
	)
	races: Mapped[list["Race"]] = relationship(
		"Race", secondary="race_languages", back_populates="languages",
	)
	backgrounds: Mapped[list["Background"]] = relationship(
		"Background",
		secondary="background_languages",
		back_populates="languages",
	)
	origins: Mapped[list["Origin"]] = relationship(
		"Origin", secondary="origin_languages", back_populates="languages",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Language")

class Creature(Base):
	"""Шаблон существа в бестиарии."""

	__tablename__ = "bestiary"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	size_id: Mapped[int] = mapped_column(
		Integer, ForeignKey("creature_sizes.id"),
		nullable=False, index=True,
	)
	type_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), ForeignKey("creature_types.id"),
		nullable=False, index=True,
	)
	alignment: Mapped[str | None] = mapped_column(
		String(50), nullable=True,
	)
	armor_class: Mapped[int] = mapped_column(Integer, nullable=False)
	armor_type_id: Mapped[int | None] = mapped_column(
		Integer, ForeignKey("armor_types.id"),
		nullable=True, index=True,
	)
	hit_points: Mapped[int] = mapped_column(Integer, nullable=False)
	hit_dice: Mapped[str | None] = mapped_column(String(20), nullable=True)
	speed_json: Mapped[dict] = mapped_column(
		JSONB, nullable=False, server_default="{}",
	)
	ability_scores: Mapped[dict] = mapped_column(
		JSONB, nullable=False, server_default="{}",
	)
	saves_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	skills_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	vulnerabilities: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	resistances: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	immunities: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	condition_immunities: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	senses_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	languages: Mapped[list[str] | None] = mapped_column(
		ARRAY(String), nullable=True,
	)
	challenge_rating: Mapped[float] = mapped_column(Float, nullable=False)
	experience_reward: Mapped[int] = mapped_column(Integer, nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
		server_default=text("now()"), onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="bestiary",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_creatures",
	)
	size: Mapped["CreatureSize"] = relationship(
		"CreatureSize", back_populates="creatures",
	)

	# Основной тип и дополнительные типы — разные связи.
	creature_type: Mapped["CreatureType"] = relationship(
		"CreatureType", foreign_keys=[type_id],
	)
	types: Mapped[list["CreatureType"]] = relationship(
		"CreatureType",
		secondary=creature_type_link,
		back_populates="creatures",
		lazy="selectin",
	)
	armor: Mapped["ArmorType | None"] = relationship("ArmorType")
	tags: Mapped[list["NPCTag"]] = relationship(
		"NPCTag",
		secondary=creature_npctag_link,
		back_populates="creatures",
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Creature")

class CreatureSize(Base):
	"""Размер существа и связанные пространственные параметры."""

	__tablename__ = "creature_sizes"
	__table_args__ = (
		UniqueConstraint(
			"system_id", "slug", name="uq_creature_sizes_system_slug",
		),
		UniqueConstraint(
			"system_id",
			"abbreviation",
			name="uq_creature_sizes_system_abbr",
		),
	)

	id: Mapped[int] = mapped_column(
		Integer, primary_key=True, autoincrement=True,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	name: Mapped[str] = mapped_column(String(20), nullable=False)
	slug: Mapped[str] = mapped_column(String(20), nullable=False)
	abbreviation: Mapped[str] = mapped_column(String(5), nullable=False)
	space_feet: Mapped[int] = mapped_column(Integer, nullable=False)
	reach_feet: Mapped[int] = mapped_column(Integer, nullable=False)
	carrying_capacity_multiplier: Mapped[float] = mapped_column(
		Float, nullable=False, server_default="1.0",
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
		server_default=text("now()"), onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="creature_sizes",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_creature_sizes",
	)
	creatures: Mapped[list["Creature"]] = relationship(
		"Creature", back_populates="size",
	)
	races: Mapped[list["Race"]] = relationship(
		"Race", back_populates="size",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="CreatureSize")

class CreatureType(Base):
	"""Справочный тип существа, общий для рас и бестиария."""

	__tablename__ = "creature_types"
	__table_args__ = (
		UniqueConstraint(
			"system_id", "slug", name="uq_creature_types_system_slug",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	name: Mapped[str] = mapped_column(String(50), nullable=False)
	slug: Mapped[str] = mapped_column(String(50), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
		server_default=text("now()"), onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="creature_types",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_creature_types",
	)
	races: Mapped[list["Race"]] = relationship(
		"Race",
		secondary=creature_type_race_link,
		back_populates="creature_types",
	)
	creatures: Mapped[list["Creature"]] = relationship(
		"Creature",
		secondary=creature_type_link,
		back_populates="types",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="CreatureType")

class NPC(Base):
	"""Конкретный неигровой персонаж, необязательно созданный по шаблону."""

	__tablename__ = "npcs"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	creature_template_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("bestiary.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	lore_entry_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("lore_entries.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	level: Mapped[int | None] = mapped_column(Integer, nullable=True)
	alignment: Mapped[str | None] = mapped_column(
		String(50), nullable=True,
	)
	armor_class: Mapped[int] = mapped_column(Integer, nullable=False)
	hit_points: Mapped[int] = mapped_column(Integer, nullable=False)
	ability_scores: Mapped[dict] = mapped_column(
		JSONB, nullable=False, server_default="{}",
	)
	saves_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	skills_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
		server_default=text("now()"), onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship("GameSystem")
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_npcs",
	)
	template: Mapped["Creature | None"] = relationship(
		"Creature", foreign_keys=[creature_template_id],
	)
	lore: Mapped["LoreEntry | None"] = relationship(
		"LoreEntry", back_populates="npcs",
	)
	tokens: Mapped[list["Token"]] = relationship(
		"Token",
		back_populates="npc",
		cascade="save-update, merge",
		passive_deletes=True,
	)
	inventory: Mapped[list["CharacterInventory"]] = relationship(
		"CharacterInventory",
		back_populates="owner_npc",
		cascade="all, delete-orphan",
	)
	tags: Mapped[list["NPCTag"]] = relationship(
		"NPCTag",
		secondary=npc_npctag_link,
		back_populates="npcs",
		lazy="selectin",
	)
	dice_rolls: Mapped[list["DiceRoll"]] = relationship(
		"DiceRoll",
		back_populates="npc",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="NPC")

class NPCTag(Base):
	"""Переиспользуемая категория НИП и шаблонов существ."""

	__tablename__ = "npc_types"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	name: Mapped[str] = mapped_column(String(50), nullable=False)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	slug: Mapped[str] = mapped_column(
		String(50), unique=True, nullable=False,
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	is_divine: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	threat_level: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
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
		server_default=text("now()"), onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="npc_types",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_npc_types",
	)

	# Тег не владеет жизненным циклом персонажей или существ.
	npcs: Mapped[list["NPC"]] = relationship(
		"NPC",
		secondary=npc_npctag_link,
		back_populates="tags",
		lazy="selectin",
	)
	creatures: Mapped[list["Creature"]] = relationship(
		"Creature",
		secondary=creature_npctag_link,
		back_populates="tags",
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="NPCTag")

class NpcTypeLink(Base):
	"""Отдельная прежняя таблица связей; сохранена для совместимости схемы."""

	__tablename__ = "npc_type_links"

	npc_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("npcs.id", ondelete="CASCADE"),
		primary_key=True,
	)
	type_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("npc_types.id", ondelete="CASCADE"),
		primary_key=True,
	)

	def __repr__(self) -> str:
		return _identity_repr(
			self, label="NpcTypeLink", keys=("npc_id", "type_id"),
		)

class LoreEntry(Base):
	"""Статья лора с необязательным родителем."""

	__tablename__ = "lore_entries"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	title: Mapped[str] = mapped_column(String(255), nullable=False)
	slug: Mapped[str] = mapped_column(String(255), nullable=False)
	content: Mapped[str] = mapped_column(Text, nullable=False)
	entry_type: Mapped[str] = mapped_column(String(50), nullable=False)
	parent_entry_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("lore_entries.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	tags_json: Mapped[list[str] | None] = mapped_column(
		JSONB, nullable=True, server_default="[]",
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
		server_default=text("now()"), onupdate=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="lore",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_lore",
	)

	# Удаление статьи не должно удалять самостоятельных персонажей.
	npcs: Mapped[list["NPC"]] = relationship(
		"NPC", back_populates="lore", passive_deletes=True,
	)
	children: Mapped[list["LoreEntry"]] = relationship(
		"LoreEntry",
		back_populates="parent_entry",
		passive_deletes=True,
	)
	parent_entry: Mapped["LoreEntry | None"] = relationship(
		"LoreEntry",
		back_populates="children",
		remote_side=[id],
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="LoreEntry")