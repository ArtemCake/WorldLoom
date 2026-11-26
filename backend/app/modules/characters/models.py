# backend/app/modules/characters/models.py

"""ORM-модели персонажей, игровых листов и их содержимого."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, Boolean, Computed, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, inspect, text)
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
			"game_system_mechanic_versions.id",
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
	content_selections: Mapped[list["CharacterContentSelection"]] = relationship(
		"CharacterContentSelection",
		back_populates="character",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	provenance_records: Mapped[list["SheetAttributeProvenance"]] = relationship(
		"SheetAttributeProvenance",
		back_populates="character",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	resource_values: Mapped[list["SheetResourceValue"]] = relationship(
		"SheetResourceValue",
		back_populates="character",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	resource_changes: Mapped[list["SheetResourceChange"]] = relationship(
		"SheetResourceChange",
		back_populates="character",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	effect_instances: Mapped[list["EffectInstance"]] = relationship(
		"EffectInstance",
		back_populates="character",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	effect_changes: Mapped[list["EffectChange"]] = relationship(
		"EffectChange",
		back_populates="character",
		cascade="all, delete-orphan",
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
			"game_system_mechanic_versions.id",
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
	provenance_records: Mapped[list["SheetAttributeProvenance"]] = relationship(
		"SheetAttributeProvenance",
		back_populates="sheet",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	resource_values: Mapped[list["SheetResourceValue"]] = relationship(
		"SheetResourceValue",
		back_populates="sheet",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	resource_changes: Mapped[list["SheetResourceChange"]] = relationship(
		"SheetResourceChange",
		back_populates="sheet",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	effect_instances: Mapped[list["EffectInstance"]] = relationship(
		"EffectInstance",
		back_populates="sheet",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	effect_changes: Mapped[list["EffectChange"]] = relationship(
		"EffectChange",
		back_populates="sheet",
		cascade="all, delete-orphan",
		passive_deletes=True,
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

# === Этап E: выбор контента и происхождение выданных свойств (§9, §13, §14.1) ===

class SheetAttributeProvenance(Base):
	"""Происхождение выданного числового свойства шаблона или листа.

	Запись принадлежит ровно одному владельцу: собственному шаблону
	(character_id) или игровому листу (character_sheet_id). Состояние
	есть у обеих записей, поэтому происхождение нужно обеим (§9).

	source_type — категория источника: race, character_class,
	background, origin, feat, equipment, effect, manual.
	source_id заполнен для элементов каталога и пуст для ручной
	правки (§14.1).

	mode описывает способ влияния источника на значение:
	- "add": источник добавляет amount; отзыв вычитает amount;
	- "set": источник устанавливает значение; отзыв возвращает
	  previous_value.

	Повторное сохранение того же источника не создаёт вторую запись
	и не меняет значение повторно: уникальность по владельцу, коду,
	типу и источнику (§9).
	"""

	__tablename__ = "sheet_attribute_provenance"

	__table_args__ = (
		CheckConstraint(
			"""
			(
				character_sheet_id IS NOT NULL
				AND character_id IS NULL
			)
			OR
			(
				character_sheet_id IS NULL
				AND character_id IS NOT NULL
			)
			""",
			name="ck_sheet_attribute_provenance_owner",
		),
		CheckConstraint(
			"source_type <> ''",
			name="ck_sheet_attribute_provenance_source_type",
		),
		CheckConstraint(
			"""
			(source_type = 'manual' AND source_id IS NULL)
			OR
			(source_type <> 'manual' AND source_id IS NOT NULL)
			""",
			name="ck_sheet_attribute_provenance_source_id",
		),
		CheckConstraint(
			"mode IN ('add', 'set')",
			name="ck_sheet_attribute_provenance_mode",
		),
		UniqueConstraint(
			"owner_key",
			"code",
			"source_type",
			"source_id",
			name="uq_sheet_attribute_provenance_source",
			postgresql_nulls_not_distinct=True,
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	character_sheet_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	character_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characters.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	# Владельцем является шаблон или лист, поэтому уникальность
	# считается по одному столбцу, а не по паре nullable-столбцов.
	owner_key: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		Computed("COALESCE(character_sheet_id, character_id)"),
		nullable=False,
	)
	code: Mapped[str] = mapped_column(String(100), nullable=False)
	source_type: Mapped[str] = mapped_column(String(30), nullable=False)
	source_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), nullable=True,
	)
	mode: Mapped[str] = mapped_column(
		String(10), nullable=False, server_default="add",
	)
	amount: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default="0",
	)
	previous_value: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default="0",
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), onupdate=text("now()"),
		server_default=text("now()"),
	)

	sheet: Mapped["CharacterSheet | None"] = relationship(
		"CharacterSheet", back_populates="provenance_records",
	)
	character: Mapped["Character | None"] = relationship(
		"Character", back_populates="provenance_records",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="SheetAttributeProvenance")

class CharacterContentSelection(Base):
	"""Выбранный персонажем элемент каталога (§9, §13).

	Один источник одного типа не может быть выбран повторно:
	уникальность по (character_id, source_type). Категории каталога
	не фиксированы — тип является данными, поэтому классовая модель
	не навязывается играм без классов (§13).

	Запись сохраняет происхождение: при отзыве элемента каталога
	по ней находят выданные свойства и снимают только их (§13).
	"""

	__tablename__ = "character_content_selections"

	__table_args__ = (
		CheckConstraint(
			"source_type <> ''",
			name="ck_character_content_selections_source_type",
		),
		UniqueConstraint(
			"character_id",
			"source_type",
			name="uq_character_content_selections_char_type",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	character_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characters.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	source_type: Mapped[str] = mapped_column(String(30), nullable=False)
	source_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), nullable=False,
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	applied_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), onupdate=text("now()"),
		server_default=text("now()"),
	)

	character: Mapped["Character"] = relationship(
		"Character", back_populates="content_selections",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="CharacterContentSelection")


# === Этап F2: значения ресурсов и журнал причин (§10) ===

class SheetResourceValue(Base):
	"""Текущий запас одного ресурса шаблона или листа.

	Значения ресурсов нельзя хранить в state_json: существующие
	CHECK-ограничения формы состояния допускают только показатели
	(ck_characters_state_shape), поэтому значения занимают
	собственную таблицу. Так сохраняется один путь записи (§1.2).

	Максимум здесь не хранится: его вычисляет существующее ядро по
	закреплённой публикации правил. Хранение максимума создало бы
	второй источник правды (§10).
	"""

	__tablename__ = "sheet_resource_values"

	__table_args__ = (
		CheckConstraint(
			"""
			(
				character_sheet_id IS NOT NULL
				AND character_id IS NULL
			)
			OR
			(
				character_sheet_id IS NULL
				AND character_id IS NOT NULL
			)
			""",
			name="ck_sheet_resource_values_owner",
		),
		CheckConstraint(
			"value >= 0",
			name="ck_sheet_resource_values_non_negative",
		),
		CheckConstraint(
			"code <> ''",
			name="ck_sheet_resource_values_code",
		),
		UniqueConstraint(
			"owner_key",
			"code",
			name="uq_sheet_resource_values_owner_code",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	character_sheet_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	character_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characters.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	owner_key: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		Computed("COALESCE(character_sheet_id, character_id)"),
		nullable=False,
	)
	code: Mapped[str] = mapped_column(String(100), nullable=False)
	value: Mapped[int] = mapped_column(Integer, nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), onupdate=text("now()"),
		server_default=text("now()"),
	)

	sheet: Mapped["CharacterSheet | None"] = relationship(
		"CharacterSheet", back_populates="resource_values",
	)
	character: Mapped["Character | None"] = relationship(
		"Character", back_populates="resource_values",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="SheetResourceValue")

class SheetResourceChange(Base):
	"""Журнал причин изменения запаса ресурса (§10).

	Договор требует, чтобы причина каждого изменения попадала в
	журнал. Запись append-only: она описывает уже выполненное
	изменение и не используется для вычисления текущего запаса.

	reason_type:
	- "init" — начальное заполнение при создании запаса;
	- "spend" — списание по стоимости действия;
	- "restore" — восстановление заданным количеством;
	- "recover" — восстановление по событию из определений ресурса;
	- "limit" — ограничение запаса политикой после смены максимума;
	- "manual" — разрешённая ручная правка.

	source_type/source_id связывают изменение с источником (например,
	предметом или эффектом), событие восстановления — с кодом события.
	"""

	__tablename__ = "sheet_resource_changes"

	__table_args__ = (
		CheckConstraint(
			"""
			(
				character_sheet_id IS NOT NULL
				AND character_id IS NULL
			)
			OR
			(
				character_sheet_id IS NULL
				AND character_id IS NOT NULL
			)
			""",
			name="ck_sheet_resource_changes_owner",
		),
		CheckConstraint(
			"""
			reason_type IN
			('init', 'spend', 'restore', 'recover', 'limit', 'manual')
			""",
			name="ck_sheet_resource_changes_reason_type",
		),
		CheckConstraint(
			"code <> ''",
			name="ck_sheet_resource_changes_code",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	character_sheet_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	character_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characters.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	owner_key: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		Computed("COALESCE(character_sheet_id, character_id)"),
		nullable=False,
	)
	code: Mapped[str] = mapped_column(String(100), nullable=False)
	reason_type: Mapped[str] = mapped_column(String(20), nullable=False)
	previous_value: Mapped[int] = mapped_column(Integer, nullable=False)
	value: Mapped[int] = mapped_column(Integer, nullable=False)
	delta: Mapped[int] = mapped_column(Integer, nullable=False)
	maximum: Mapped[int | None] = mapped_column(Integer, nullable=True)
	event_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
	source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
	source_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), nullable=True,
	)
	comment: Mapped[str | None] = mapped_column(Text, nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
		index=True,
	)

	sheet: Mapped["CharacterSheet | None"] = relationship(
		"CharacterSheet", back_populates="resource_changes",
	)
	character: Mapped["Character | None"] = relationship(
		"Character", back_populates="resource_changes",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="SheetResourceChange")

# === Этап F3: экземпляры эффектов на цели и журнал причин (§12) ===

class EffectInstance(Base):
	"""Экземпляр эффекта, наложенный на цель (§12).

	Эффект имеет отдельный экземпляр, источник, цель, изменения,
	условия, правила сочетания, начало, длительность и события
	прекращения (§12). Идентичность даёт первичный ключ экземпляра,
	а не название: совпадение названия с другим экземпляром не
	объединяет их и не позволяет снять один вместо другого.

	Цель принадлежит ровно одному владельцу: игровому листу или
	собственному шаблону (§14.1), как у ресурсов и происхождения.

	Изменения и правила сочетания хранятся данными (массив
	modifiers), а не вычисляемым итогом: итог сворачивает ядро
	effect_stacking.combine_modifier по активным экземплярам, поэтому
	второго источника правды об итоге нет (§12).

	Длительность и события прекращения сохраняются как данные.
	Течение игрового времени и автоматическое истечение относятся к
	исполнению процедур (§30#6, этап H) и здесь не вычисляются.
	"""

	__tablename__ = "effect_instances"

	__table_args__ = (
		CheckConstraint(
			"""
			(
				character_sheet_id IS NOT NULL
				AND character_id IS NULL
			)
			OR
			(
				character_sheet_id IS NULL
				AND character_id IS NOT NULL
			)
			""",
			name="ck_effect_instances_owner",
		),
		CheckConstraint(
			"status IN ('active', 'suppressed', 'withdrawn')",
			name="ck_effect_instances_status",
		),
		CheckConstraint(
			"jsonb_typeof(modifiers) = 'array'",
			name="ck_effect_instances_modifiers_array",
		),
		CheckConstraint(
			"source_type <> ''",
			name="ck_effect_instances_source_type",
		),
		UniqueConstraint(
			"owner_key",
			"application_key",
			name="uq_effect_instances_application_key",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	character_sheet_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	character_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characters.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	owner_key: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		Computed("COALESCE(character_sheet_id, character_id)"),
		nullable=False,
	)
	# Идентичность экземпляра — его id. Название эффекта не идентичность.
	status: Mapped[str] = mapped_column(
		String(20), nullable=False, server_default="active",
	)
	# Описание-источник из каталога (может отсутствовать для ручного
	# наложения); при удалении описания экземпляр сохраняется (§12).
	effect_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("effects.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	source_type: Mapped[str] = mapped_column(String(30), nullable=False)
	source_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), nullable=True,
	)
	# Идемпотентный ключ наложения: повторная обработка одного события
	# с тем же ключом переиспользует экземпляр, а не создаёт копию (§12).
	application_key: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), nullable=True,
	)
	# Изменения и правила сочетания: [{"code","value","stacking","priority"}].
	modifiers: Mapped[list] = mapped_column(
		JSONB(none_as_null=True), nullable=False, server_default=text("'[]'::jsonb"),
	)
	# Условия действия — данные для исполнения; здесь не интерпретируются.
	conditions: Mapped[dict | None] = mapped_column(
		JSONB(none_as_null=True), nullable=True,
	)
	duration_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
	duration_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
	# События прекращения — коды, по которым экземпляр снимается (§12).
	end_events: Mapped[list | None] = mapped_column(
		JSONB(none_as_null=True), nullable=True,
	)
	started_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	started_event: Mapped[str | None] = mapped_column(String(100), nullable=True)
	ended_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True), nullable=True,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), onupdate=text("now()"),
		server_default=text("now()"),
	)

	sheet: Mapped["CharacterSheet | None"] = relationship(
		"CharacterSheet", back_populates="effect_instances",
	)
	character: Mapped["Character | None"] = relationship(
		"Character", back_populates="effect_instances",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="EffectInstance")

class EffectChange(Base):
	"""Журнал причин наложения, продления, подавления и снятия (§12).

	Запись append-only описывает уже выполненное действие над
	экземпляром и служит причиной этого действия; она не участвует в
	вычислении свёртки эффектов.

	reason_type:
	- "apply" — наложение экземпляра;
	- "extend" — продление длительности;
	- "suppress" — подавление экземпляра (переход статуса);
	- "withdraw" — снятие экземпляра.

	status_before/status_after фиксируют переход жизненного статуса
	экземпляра. request_id связывает запись с запросом процедуры,
	чтобы повтор одного события не снял эффект дважды (§12).
	"""

	__tablename__ = "effect_changes"

	__table_args__ = (
		CheckConstraint(
			"""
			(
				character_sheet_id IS NOT NULL
				AND character_id IS NULL
			)
			OR
			(
				character_sheet_id IS NULL
				AND character_id IS NOT NULL
			)
			""",
			name="ck_effect_changes_owner",
		),
		CheckConstraint(
			"reason_type IN ('apply', 'extend', 'suppress', 'withdraw')",
			name="ck_effect_changes_reason_type",
		),
		CheckConstraint(
			"status_after IN ('active', 'suppressed', 'withdrawn')",
			name="ck_effect_changes_status_after",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	character_sheet_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	character_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("characters.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	owner_key: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		Computed("COALESCE(character_sheet_id, character_id)"),
		nullable=False,
	)
	# Экземпляр может быть удалён позже; журнал остаётся для аудита (§12).
	instance_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("effect_instances.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	reason_type: Mapped[str] = mapped_column(String(20), nullable=False)
	status_before: Mapped[str | None] = mapped_column(String(20), nullable=True)
	status_after: Mapped[str] = mapped_column(String(20), nullable=False)
	event_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
	request_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), nullable=True,
	)
	source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
	source_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True), nullable=True,
	)
	comment: Mapped[str | None] = mapped_column(Text, nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
		index=True,
	)

	sheet: Mapped["CharacterSheet | None"] = relationship(
		"CharacterSheet", back_populates="effect_changes",
	)
	character: Mapped["Character | None"] = relationship(
		"Character", back_populates="effect_changes",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="EffectChange")
