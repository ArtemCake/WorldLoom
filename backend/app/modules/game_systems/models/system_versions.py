# backend/app/modules/game_systems/models/system_versions.py

"""ORM-модели раздельных правил, механики и комплекта игровой системы.

Игровая система — это карточка (название, описание) и набор версий.
Каждая версия системы (комплект) связывает собственную версию
текстовых правил и собственную версию механики.

- Правила (текст): редактируемый черновик и опубликованные снимки
  раздела rulebook (главы, поля, состояние «проектируется/описано/
  не используется»). Механику не содержат.
- Механика (формулы): редактируемый черновик и опубликованные снимки
  исполняемого числового профиля (calculations, initial_attributes,
  resources) с происхождением от версии движка.
- Комплект: опубликованная версия системы, привязанная к версии
  правил и версии механики. Механика обязательна (исполнимая
  публикация), текстовая книга необязательна (система без книг).

Эти модели — единственный состав публикации системы: прежняя единая
таблица правил упразднена, её место занимает пара «механика + текст»
и комплект, связывающий их в опубликованную версию.
"""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
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


class GameSystemTextDraft(Base):
	"""Черновик текстовых правил системы с проверкой конкурентных изменений."""

	__tablename__ = "game_system_text_drafts"

	__table_args__ = (
		UniqueConstraint("system_id", name="uq_game_system_text_drafts_system"),
		CheckConstraint(
			"revision >= 1",
			name="ck_game_system_text_drafts_revision_positive",
		),
		CheckConstraint(
			"jsonb_typeof(text_json) = 'object'",
			name="ck_game_system_text_drafts_text_object",
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
	# Раздел текста: {"schema_version": 1, "chapters": {код: глава}}.
	text_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
	revision: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		default=1,
		server_default=text("1"),
	)
	is_published: Mapped[bool] = mapped_column(
		Boolean,
		nullable=False,
		default=False,
		server_default=text("false"),
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

	__mapper_args__ = {"version_id_col": revision}

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystemTextDraft")


class GameSystemTextVersion(Base):
	"""Опубликованный неизменяемый снимок текстовых правил системы."""

	__tablename__ = "game_system_text_versions"

	__table_args__ = (
		UniqueConstraint(
			"system_id",
			"version_number",
			name="uq_game_system_text_versions_number",
		),
		# Составной ключ для ссылки комплекта в той же системе.
		UniqueConstraint("system_id", "id", name="uq_game_system_text_versions_system_id"),
		CheckConstraint(
			"version_number >= 1",
			name="ck_game_system_text_versions_number_positive",
		),
		CheckConstraint(
			"source_draft_revision >= 1",
			name="ck_game_system_text_versions_source_revision",
		),
		CheckConstraint(
			"jsonb_typeof(text_json) = 'object'",
			name="ck_game_system_text_versions_text_object",
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
	version_number: Mapped[int] = mapped_column(Integer, nullable=False)
	source_draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
	text_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
	published_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		foreign_keys="GameSystemTextVersion.system_id",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystemTextVersion")


class GameSystemMechanicDraft(Base):
	"""Черновик механики системы: исполняемый числовой профиль."""

	__tablename__ = "game_system_mechanic_drafts"

	__table_args__ = (
		UniqueConstraint("system_id", name="uq_game_system_mechanic_drafts_system"),
		CheckConstraint(
			"revision >= 1",
			name="ck_game_system_mechanic_drafts_revision_positive",
		),
		CheckConstraint(
			"jsonb_typeof(mechanic_json) = 'object'",
			name="ck_game_system_mechanic_drafts_mechanic_object",
		),
		CheckConstraint(
			"""
			(
				engine_version_id IS NULL
				AND mechanic_overrides_json IS NULL
			)
			OR
			(
				engine_version_id IS NOT NULL
				AND mechanic_overrides_json IS NOT NULL
				AND jsonb_typeof(mechanic_overrides_json) = 'object'
			)
			""",
			name="ck_game_system_mechanic_drafts_engine_origin",
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
	# Происхождение механики от опубликованной версии движка (опционально).
	engine_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("rule_engine_versions.id", ondelete="RESTRICT"),
		nullable=True,
		index=True,
	)
	# Разделы, переопределённые автором относительно основы движка.
	mechanic_overrides_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
	# Исполняемый профиль без текста: {schema_version, calculations,
	# initial_attributes, resources}.
	mechanic_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
	revision: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		default=1,
		server_default=text("1"),
	)
	is_published: Mapped[bool] = mapped_column(
		Boolean,
		nullable=False,
		default=False,
		server_default=text("false"),
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

	__mapper_args__ = {"version_id_col": revision}

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystemMechanicDraft")


class GameSystemMechanicVersion(Base):
	"""Опубликованный неизменяемый снимок механики системы."""

	__tablename__ = "game_system_mechanic_versions"

	__table_args__ = (
		UniqueConstraint(
			"system_id",
			"version_number",
			name="uq_game_system_mechanic_versions_number",
		),
		UniqueConstraint(
			"system_id",
			"id",
			name="uq_game_system_mechanic_versions_system_id",
		),
		CheckConstraint(
			"version_number >= 1",
			name="ck_game_system_mechanic_versions_number_positive",
		),
		CheckConstraint(
			"source_draft_revision >= 1",
			name="ck_game_system_mechanic_versions_source_revision",
		),
		CheckConstraint(
			"jsonb_typeof(mechanic_json) = 'object'",
			name="ck_game_system_mechanic_versions_mechanic_object",
		),
		CheckConstraint(
			"""
			(
				engine_version_id IS NULL
				AND mechanic_overrides_json IS NULL
			)
			OR
			(
				engine_version_id IS NOT NULL
				AND mechanic_overrides_json IS NOT NULL
				AND jsonb_typeof(mechanic_overrides_json) = 'object'
			)
			""",
			name="ck_game_system_mechanic_versions_engine_origin",
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
	version_number: Mapped[int] = mapped_column(Integer, nullable=False)
	source_draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
	engine_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("rule_engine_versions.id", ondelete="RESTRICT"),
		nullable=True,
		index=True,
	)
	mechanic_overrides_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
	mechanic_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
	# Версия программного исполнителя, а не номер публикации системы.
	rules_engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
	published_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		foreign_keys="GameSystemMechanicVersion.system_id",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystemMechanicVersion")


class GameSystemVersion(Base):
	"""Комплект: опубликованная версия системы, связывающая правила и механику.

	Механика обязательна (исполнимая публикация), текстовая версия
	необязательна (допустима система без книг). Обе ссылки закреплены
	за той же системой составным уникальным ключом.
	"""

	__tablename__ = "game_system_versions"

	__table_args__ = (
		UniqueConstraint(
			"system_id",
			"version_number",
			name="uq_game_system_versions_number",
		),
		UniqueConstraint(
			"system_id",
			"id",
			name="uq_game_system_versions_system_id",
		),
		CheckConstraint(
			"version_number >= 1",
			name="ck_game_system_versions_number_positive",
		),
		# Составные ключи закрепляют версии комплекта за той же системой:
		# подставить версию чужой системы на уровне схемы невозможно.
		ForeignKeyConstraint(
			["system_id", "text_version_id"],
			[
				"game_system_text_versions.system_id",
				"game_system_text_versions.id",
			],
			ondelete="RESTRICT",
			name="fk_game_system_versions_text",
		),
		ForeignKeyConstraint(
			["system_id", "mechanic_version_id"],
			[
				"game_system_mechanic_versions.system_id",
				"game_system_mechanic_versions.id",
			],
			ondelete="RESTRICT",
			name="fk_game_system_versions_mechanic",
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
	version_number: Mapped[int] = mapped_column(Integer, nullable=False)
	text_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		nullable=True,
		index=True,
	)
	mechanic_version_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		nullable=False,
		index=True,
	)
	published_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)

	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		foreign_keys="GameSystemVersion.system_id",
	)
	text_version: Mapped["GameSystemTextVersion | None"] = relationship(
		"GameSystemTextVersion",
		foreign_keys="GameSystemVersion.text_version_id",
	)
	mechanic_version: Mapped["GameSystemMechanicVersion"] = relationship(
		"GameSystemMechanicVersion",
		foreign_keys="GameSystemVersion.mechanic_version_id",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="GameSystemVersion")
