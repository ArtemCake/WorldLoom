# backend/app/modules/users/models/user.py

"""ORM-модель пользователя."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, CheckConstraint, DateTime, Integer, String, Text, func, inspect, text)
from sqlalchemy.dialects.postgresql import (ARRAY, ENUM, JSONB, UUID as PG_UUID)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base
from backend.app.modules.users.enums import (AdminPermission, SystemRole)


_SYSTEM_ROLE_TYPE = ENUM(
	SystemRole,
	name="system_role_type",
	create_type=True,
	validate_strings=True,
	values_callable=lambda enum_class: [
		member.value for member in enum_class
	],
)

_ADMIN_PERMISSION_TYPE = ENUM(
	AdminPermission,
	name="admin_permission_type",
	create_type=True,
	validate_strings=True,
	values_callable=lambda enum_class: [
		member.value for member in enum_class
	],
)

class User(Base):
	"""Учётные данные, профиль и связи пользователя."""

	__tablename__ = "users"
	__table_args__ = (
		CheckConstraint(
			r"nickname !~ '^\s+$'",
			name="ck_user_nickname_not_blank",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
		nullable=False,
	)
	email_encrypted: Mapped[str] = mapped_column(String(500))
	email_hash: Mapped[str] = mapped_column(
		String(64),
		unique=True,
		index=True,
	)
	password_hash: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	nickname: Mapped[str] = mapped_column(
		String(50),
		nullable=False,
		index=True,
		unique=True,
	)
	maps_storage_folder: Mapped[str | None] = mapped_column(
		String(160),
		nullable=True,
	)
	avatar_url: Mapped[str | None] = mapped_column(
		String(500),
		nullable=True,
	)
	profile_settings: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	is_email_verified: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
		nullable=False,
	)
	is_2fa_enabled: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
		nullable=False,
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
		onupdate=func.now(),
		nullable=False,
	)
	last_login: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		nullable=True,
	)
	active_session_token: Mapped[str | None] = mapped_column(
		String(512),
		index=True,
		nullable=True,
	)
	roles: Mapped[list[SystemRole]] = mapped_column(
		ARRAY(_SYSTEM_ROLE_TYPE),
		nullable=False,
		server_default=text("'{player}'::system_role_type[]"),
	)
	failed_login_attempts: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		server_default=text("0"),
	)
	locked_until: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		nullable=True,
	)
	admin_permissions: Mapped[list[AdminPermission]] = mapped_column(
		ARRAY(_ADMIN_PERMISSION_TYPE),
		nullable=False,
		server_default=text("'{}'::admin_permission_type[]"),
	)
	deleted_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		nullable=True,
	)

	friends_from: Mapped[list["Friendship"]] = relationship(
		"Friendship",
		back_populates="user",
		foreign_keys="[Friendship.user_id]",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	friends_to: Mapped[list["Friendship"]] = relationship(
		"Friendship",
		back_populates="friend",
		foreign_keys="[Friendship.friend_user_id]",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	oauth_providers: Mapped[list["OAuthProvider"]] = relationship(
		"OAuthProvider",
		back_populates="user",
		cascade="all, delete-orphan",
	)
	mfa_devices: Mapped[list["MFADevice"]] = relationship(
		"MFADevice",
		back_populates="user",
		cascade="all, delete-orphan",
	)
	created_games: Mapped[list["Game"]] = relationship(
		"Game",
		back_populates="master",
	)
	dice_rolls: Mapped[list["DiceRoll"]] = relationship(
		"DiceRoll",
		back_populates="roller",
	)
	chat_messages: Mapped[list["Message"]] = relationship(
		"Message",
		back_populates="sender",
	)
	uploaded_assets: Mapped[list["UploadedAsset"]] = relationship(
		"UploadedAsset",
		back_populates="uploader",
		cascade="all, delete-orphan",
	)
	audit_logs: Mapped[list["AuditLog"]] = relationship(
		"AuditLog",
		back_populates="user",
	)
	content_reports: Mapped[list["ContentReport"]] = relationship(
		"ContentReport",
		back_populates="reporter",
		foreign_keys="ContentReport.reporter_id",
	)

	created_spells: Mapped[list["Spell"]] = relationship(
		"Spell",
		back_populates="owner",
	)
	created_races: Mapped[list["Race"]] = relationship(
		"Race",
		back_populates="owner",
	)
	created_languages: Mapped[list["Language"]] = relationship(
		"Language",
		back_populates="owner",
	)
	created_npcs: Mapped[list["NPC"]] = relationship(
		"NPC",
		back_populates="owner",
		cascade="save-update, merge",
		passive_deletes=True,
	)
	created_npc_types: Mapped[list["NPCTag"]] = relationship(
		"NPCTag",
		back_populates="owner",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)
	created_lore: Mapped[list["LoreEntry"]] = relationship(
		"LoreEntry",
		back_populates="owner",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)
	created_origins: Mapped[list["Origin"]] = relationship(
		"Origin",
		back_populates="owner",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)
	created_damage_types: Mapped[list["DamageType"]] = relationship(
		"DamageType",
		back_populates="owner",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)
	created_armor_types: Mapped[list["ArmorType"]] = relationship(
		"ArmorType",
		back_populates="owner",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)
	created_characters: Mapped[list["Character"]] = relationship(
		"Character",
		back_populates="owner",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	created_ai_jobs: Mapped[list["AIGenerationJob"]] = relationship(
		"AIGenerationJob",
		back_populates="owner",
		cascade="all, delete-orphan",
		lazy="selectin",
	)
	created_homebrew_rules: Mapped[list["HomebrewRule"]] = relationship(
		"HomebrewRule",
		back_populates="owner",
	)
	created_creatures: Mapped[list["Creature"]] = relationship(
		"Creature",
		back_populates="owner",
	)
	created_creature_sizes: Mapped[list["CreatureSize"]] = relationship(
		"CreatureSize",
		back_populates="owner",
		lazy="selectin",
	)
	created_creature_types: Mapped[list["CreatureType"]] = relationship(
		"CreatureType",
		back_populates="owner",
		lazy="selectin",
	)
	created_classes: Mapped[list["CharacterClass"]] = relationship(
		"CharacterClass",
		back_populates="owner",
		lazy="selectin",
	)
	created_subclasses: Mapped[list["Subclass"]] = relationship(
		"Subclass",
		back_populates="owner",
		lazy="selectin",
	)
	created_backgrounds: Mapped[list["Background"]] = relationship(
		"Background",
		back_populates="owner",
		lazy="selectin",
	)
	created_feats: Mapped[list["Feat"]] = relationship(
		"Feat",
		back_populates="owner",
		lazy="selectin",
	)
	created_skills: Mapped[list["Skill"]] = relationship(
		"Skill",
		back_populates="owner",
		lazy="selectin",
	)
	skill_char_maps: Mapped[list["SkillCharacteristicMap"]] = relationship(
		"SkillCharacteristicMap",
		back_populates="owner",
		lazy="selectin",
	)
	created_spell_levels: Mapped[list["SpellSlot"]] = relationship(
		"SpellSlot",
		back_populates="owner",
		lazy="selectin",
	)
	created_magic_schools: Mapped[list["MagicSchool"]] = relationship(
		"MagicSchool",
		back_populates="owner",
		lazy="selectin",
	)
	created_abilities: Mapped[list["Ability"]] = relationship(
		"Ability",
		back_populates="owner",
		lazy="selectin",
	)
	created_effects: Mapped[list["Effect"]] = relationship(
		"Effect",
		back_populates="owner",
		lazy="selectin",
	)
	created_equipment: Mapped[list["Equipment"]] = relationship(
		"Equipment",
		back_populates="owner",
		lazy="selectin",
	)
	created_item_types: Mapped[list["ItemType"]] = relationship(
		"ItemType",
		back_populates="owner",
		lazy="selectin",
	)
	created_rarities: Mapped[list["Rarity"]] = relationship(
		"Rarity",
		back_populates="owner",
		lazy="selectin",
	)
	created_weapon_types: Mapped[list["WeaponType"]] = relationship(
		"WeaponType",
		back_populates="owner",
		lazy="selectin",
	)
	created_map_objects: Mapped[list["MapObject"]] = relationship(
		"MapObject",
		back_populates="owner",
		lazy="selectin",
	)

	@property
	def email(self) -> str:
		"""Совместимый интерфейс чтения зашифрованного email."""
		from backend.app.core.crypto import decrypt_value

		return decrypt_value(self.email_encrypted)

	@email.setter
	def email(self, value: str) -> None:
		"""Сохранить шифротекст и поисковый HMAC."""
		from backend.app.core.crypto import encrypt_value, hash_email

		# Сначала вычисляем оба значения. При ошибке вычисления
		# не оставляем объект с обновлённым только одним полем.
		encrypted = encrypt_value(value)
		email_hash = hash_email(value)

		self.email_encrypted = encrypted
		self.email_hash = email_hash

	def __repr__(self) -> str:
		"""Представление без расшифровки и загрузки атрибутов."""
		state = inspect(self)

		identifier = (
			state.identity[0]
			if state.identity is not None
			else state.dict.get("id")
		)

		return f"<User(id={identifier!r})>"