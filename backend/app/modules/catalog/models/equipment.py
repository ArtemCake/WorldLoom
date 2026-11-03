# backend/app/modules/catalog/models/equipment.py

"""Модели снаряжения, оружия, доспехов и магических предметов."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, inspect, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
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

class Equipment(Base):
	"""Базовый предмет снаряжения."""

	__tablename__ = "equipment"

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
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	item_type_id: Mapped[int] = mapped_column(
		Integer, ForeignKey("item_types.id"),
		nullable=False, index=True,
	)
	rarity_id: Mapped[int | None] = mapped_column(
		Integer, ForeignKey("rarities.id"),
		nullable=True, index=True,
	)
	weight: Mapped[float | None] = mapped_column(Float, nullable=True)
	cost: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default=text("'{\"gp\": 0}'::jsonb"),
	)
	properties_json: Mapped[dict | None] = mapped_column(
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
		"GameSystem", back_populates="equipment",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_equipment",
	)
	type_obj: Mapped["ItemType"] = relationship("ItemType")
	rarity: Mapped["Rarity | None"] = relationship("Rarity")
	weapons: Mapped[list["Weapon"]] = relationship(
		"Weapon", back_populates="base_item",
		cascade="all, delete-orphan",
	)
	armor: Mapped[list["Armor"]] = relationship(
		"Armor", back_populates="base_item",
		cascade="all, delete-orphan",
	)
	magical_items: Mapped[list["MagicalItem"]] = relationship(
		"MagicalItem", back_populates="base_item",
		cascade="all, delete-orphan",
	)
	artifacts: Mapped[list["Artifact"]] = relationship(
		"Artifact", back_populates="base_item",
		cascade="all, delete-orphan", uselist=True,
	)
	assets: Mapped[list["UploadedAsset"]] = relationship(
		"UploadedAsset",
		back_populates="equipment",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Equipment")

class ItemType(Base):
	"""Иерархический справочник типов предметов."""

	__tablename__ = "item_types"

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
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	slug: Mapped[str] = mapped_column(String(100), nullable=False)
	parent_type_id: Mapped[int | None] = mapped_column(
		Integer, ForeignKey("item_types.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	is_gear_slot: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	slot_name: Mapped[str | None] = mapped_column(
		String(50), nullable=True,
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
		"GameSystem", back_populates="item_types",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_item_types",
	)
	equipment: Mapped[list["Equipment"]] = relationship(
		"Equipment", back_populates="type_obj",
	)
	children: Mapped[list["ItemType"]] = relationship(
		"ItemType", backref=backref("parent", remote_side=[id]),
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="ItemType")

class Rarity(Base):
	"""Уровень редкости предмета."""

	__tablename__ = "rarities"
	__table_args__ = (
		UniqueConstraint(
			"system_id", "slug", name="uq_rarities_system_slug",
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
	name: Mapped[str] = mapped_column(String(50), nullable=False)
	slug: Mapped[str] = mapped_column(String(50), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	sort_order: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default="0",
	)
	color_theme: Mapped[str | None] = mapped_column(
		String(7), nullable=True,
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
		"GameSystem", back_populates="rarities",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_rarities",
	)
	equipment: Mapped[list["Equipment"]] = relationship(
		"Equipment", back_populates="rarity",
	)
	magical_items: Mapped[list["MagicalItem"]] = relationship(
		"MagicalItem", back_populates="rarity",
	)
	artifacts: Mapped[list["Artifact"]] = relationship(
		"Artifact", back_populates="rarity",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Rarity")

class Weapon(Base):
	"""Боевые параметры оружия поверх базового предмета."""

	__tablename__ = "weapons"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	base_item_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("equipment.id", ondelete="CASCADE"),
		nullable=False, unique=True, index=True,
	)
	weapon_type_id: Mapped[int] = mapped_column(
		Integer, ForeignKey("weapon_types.id"),
		nullable=False, index=True,
	)
	weapon_class_id: Mapped[int | None] = mapped_column(
		Integer, ForeignKey("weapon_classes.id"),
		nullable=True, index=True,
	)
	damage_dice: Mapped[str] = mapped_column(
		String(20), nullable=False,
	)
	damage_type_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("damage_types.id", ondelete="SET NULL"),
		nullable=True, index=True,
	)
	properties_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	range_normal: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	range_long: Mapped[int | None] = mapped_column(
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
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	base_item: Mapped["Equipment"] = relationship(
		"Equipment", back_populates="weapons",
	)
	type_obj: Mapped["WeaponType"] = relationship(
		"WeaponType",
		back_populates="weapons",
	)
	weapon_class: Mapped["WeaponClass | None"] = relationship(
		"WeaponClass",
		back_populates="weapons",
	)
	damage_type: Mapped["DamageType | None"] = relationship("DamageType")

	def __repr__(self) -> str:
		return _identity_repr(self, label="Weapon")

class WeaponType(Base):
	"""Справочник типов оружия."""

	__tablename__ = "weapon_types"
	__table_args__ = (
		UniqueConstraint(
			"system_id", "slug", name="uq_weapon_types_system_slug",
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
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="weapon_types",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_weapon_types",
	)
	weapons: Mapped[list["Weapon"]] = relationship(
		"Weapon",
		back_populates="type_obj",
		cascade="save-update, merge",
		passive_deletes="all",
	)
	classes: Mapped[list["WeaponClass"]] = relationship(
		"WeaponClass",
		back_populates="weapon_type",
		cascade="save-update, merge",
		passive_deletes="all",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="WeaponType")

class WeaponClass(Base):
	"""Класс оружия внутри его типа."""

	__tablename__ = "weapon_classes"

	id: Mapped[int] = mapped_column(
		Integer, primary_key=True, autoincrement=True,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	type_id: Mapped[int] = mapped_column(
		Integer, ForeignKey("weapon_types.id", ondelete="CASCADE"),
		nullable=False, index=True,
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
		onupdate=text("now()"),
		server_default=text("now()"),
	)
	system: Mapped["GameSystem"] = relationship("GameSystem")
	weapon_type: Mapped["WeaponType"] = relationship(
		"WeaponType",
		back_populates="classes",
	)
	weapons: Mapped[list["Weapon"]] = relationship(
		"Weapon",
		back_populates="weapon_class",
		cascade="save-update, merge",
		passive_deletes="all",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="WeaponClass")

class Armor(Base):
	"""Защитные параметры доспеха поверх базового предмета."""

	__tablename__ = "armor"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	base_item_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("equipment.id", ondelete="CASCADE"),
		nullable=False, unique=True, index=True,
	)
	armor_type_id: Mapped[int] = mapped_column(
		Integer, ForeignKey("armor_types.id"),
		nullable=False, index=True,
	)
	base_armor_class: Mapped[int] = mapped_column(
		Integer, nullable=False,
	)
	requires_stealth_disadvantage: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	strength_requirement: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	is_heavy: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	max_dex_bonus: Mapped[int | None] = mapped_column(
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
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	base_item: Mapped["Equipment"] = relationship(
		"Equipment", back_populates="armor",
	)
	type_obj: Mapped["ArmorType"] = relationship(
		"ArmorType",
		back_populates="armor",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Armor")

class ArmorType(Base):
	"""Тип доспеха; глобальная уникальность имён сохранена."""

	__tablename__ = "armor_types"

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
	name: Mapped[str] = mapped_column(
		String(50), unique=True, nullable=False,
	)
	slug: Mapped[str] = mapped_column(
		String(50), unique=True, nullable=False,
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	is_shield: Mapped[bool] = mapped_column(
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
		onupdate=text("now()"),
		server_default=text("now()"),
	)
	system: Mapped["GameSystem"] = relationship(
		"GameSystem", back_populates="armor_types",
	)
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_armor_types",
	)
	armor: Mapped[list["Armor"]] = relationship(
		"Armor",
		back_populates="type_obj",
		cascade="save-update, merge",
		passive_deletes="all",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="ArmorType")

class MagicalItem(Base):
	"""Магические свойства базового предмета."""

	__tablename__ = "magical_items"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	base_item_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("equipment.id", ondelete="CASCADE"),
		nullable=False, unique=True, index=True,
	)
	rarity_id: Mapped[int] = mapped_column(
		Integer, ForeignKey("rarities.id"),
		nullable=False, index=True,
	)
	requires_attunement: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	attunement_restriction: Mapped[str | None] = mapped_column(
		String(255), nullable=True,
	)
	charges_max: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	charges_current: Mapped[int | None] = mapped_column(
		Integer, nullable=True,
	)
	recharge_condition: Mapped[str | None] = mapped_column(
		String(100), nullable=True,
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	lore_description: Mapped[str | None] = mapped_column(
		Text, nullable=True,
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

	base_item: Mapped["Equipment"] = relationship(
		"Equipment", back_populates="magical_items",
	)
	rarity: Mapped["Rarity"] = relationship(
		"Rarity", back_populates="magical_items",
	)
	effects: Mapped[list["Effect"]] = relationship(
		"Effect",
		secondary="item_effects",
		back_populates="magical_items",
		cascade="save-update, merge",
		passive_deletes=True,
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="MagicalItem")

class ItemEffect(Base):
	"""Связь магического предмета и эффекта."""

	__tablename__ = "item_effects"

	item_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("magical_items.id", ondelete="CASCADE"),
		primary_key=True,
	)
	effect_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("effects.id", ondelete="CASCADE"),
		primary_key=True,
	)

	def __repr__(self) -> str:
		return _identity_repr(
			self, label="ItemEffect", keys=("item_id", "effect_id"),
		)

class Artifact(Base):
	"""Артефакт, связанный непосредственно с базовым предметом."""

	__tablename__ = "artifacts"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	base_item_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("equipment.id", ondelete="CASCADE"),
		nullable=False, unique=True, index=True,
	)
	rarity_id: Mapped[int] = mapped_column(
		Integer, ForeignKey("rarities.id"),
		nullable=False, index=True,
	)
	destruction_requirements: Mapped[str | None] = mapped_column(
		Text, nullable=True,
	)
	is_sentient: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	sentience_profile: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	curses_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	requires_attunement: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	lore_description: Mapped[str | None] = mapped_column(
		Text, nullable=True,
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

	rarity: Mapped["Rarity"] = relationship(
		"Rarity", back_populates="artifacts",
	)
	properties: Mapped[list["ArtifactProperty"]] = relationship(
		"ArtifactProperty", back_populates="artifact",
		cascade="all, delete-orphan",
	)
	base_item: Mapped["Equipment"] = relationship(
		"Equipment",
		back_populates="artifacts",
		cascade="save-update, merge",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Artifact")

class ArtifactProperty(Base):
	"""Отдельное свойство артефакта."""

	__tablename__ = "artifact_properties"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	artifact_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("artifacts.id", ondelete="CASCADE"),
		nullable=False, index=True,
	)
	property_type: Mapped[str] = mapped_column(
		String(50), nullable=False,
	)
	payload_json: Mapped[dict] = mapped_column(
		JSONB, nullable=False, server_default="{}",
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

	artifact: Mapped["Artifact"] = relationship(
		"Artifact", back_populates="properties",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="ArtifactProperty")