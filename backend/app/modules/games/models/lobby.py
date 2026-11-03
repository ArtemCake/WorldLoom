# backend/app/modules/games/models/lobby.py

"""ORM-модели игрового лобби и состояния игровой встречи.

Описание таблиц перенесено из старого Gameplay/lobby.py.
Импорт модуля не загружает настройки и не открывает соединения.
"""

from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, inspect, text)
from sqlalchemy.dialects.postgresql import (ARRAY, JSONB, UUID as PG_UUID)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str, field: str = "id") -> str:
	"""Сформировать представление без загрузки ORM-атрибутов.

	Применяется только к несекретным идентификаторам.
	Для Invite не используется: его первичный ключ — токен.
	"""
	state = inspect(instance)
	identifier = (
		state.identity[0]
		if state.identity is not None
		else state.dict.get(field)
	)
	return f"<{label}({field}={identifier!r})>"

class Game(Base):
	"""Игра или кампания с выбранной игровой системой."""

	__tablename__ = "games"
	__table_args__ = (
		ForeignKeyConstraint(
			["system_id", "rules_version_id"],
			[
				"game_system_rules_versions.system_id",
				"game_system_rules_versions.id",
			],
			name="fk_games_rules_version_same_system",
			ondelete="RESTRICT",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	master_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	system_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("game_systems.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	rules_version_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		nullable=True,
		index=True,
	)
	title: Mapped[str] = mapped_column(
		String(255),
		nullable=False,
	)
	description: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	status: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default="draft",
	)
	privacy_level: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default="private",
	)
	voice_chat_config: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)
	is_homebrew_allowed: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
		nullable=False,
	)
	maps_storage_folder: Mapped[str | None] = mapped_column(
		String(160),
		nullable=True,
	)
	next_map_number: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		default=1,
		server_default="1",
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
	master: Mapped["User | None"] = relationship(
		"User",
		back_populates="created_games",
	)
	system: Mapped["GameSystem"] = relationship(
		"GameSystem",
		foreign_keys=[system_id],
	)
	rules_version: Mapped["GameSystemRulesVersion | None"] = relationship(
		"GameSystemRulesVersion",
		foreign_keys=[rules_version_id],
		lazy="raise",
	)
	party: Mapped[list["Party"]] = relationship(
		"Party",
		back_populates="game",
		cascade="all, delete-orphan",
	)
	invites: Mapped[list["Invite"]] = relationship(
		"Invite",
		back_populates="game",
		cascade="all, delete-orphan",
	)
	sessions: Mapped[list["Session"]] = relationship(
		"Session",
		back_populates="game",
		cascade="all, delete-orphan",
	)
	campaign_maps: Mapped[list["CampaignMap"]] = relationship(
		"CampaignMap",
		back_populates="game",
		cascade="all, delete-orphan",
	)
	character_sheets: Mapped[list["CharacterSheet"]] = relationship(
		"CharacterSheet",
		back_populates="game",
		cascade="all, delete-orphan",
		passive_deletes=True,
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Game")

class Party(Base):
	"""Участие пользователя в игре."""

	__tablename__ = "party"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
		index=True,
	)
	game_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("games.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	user_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	joined_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)
	role_in_game: Mapped[str] = mapped_column(
		String(20),
		nullable=False,
		server_default="player",
	)
	is_active: Mapped[bool] = mapped_column(
		Boolean,
		default=True,
		nullable=False,
	)
	notification_settings: Mapped[dict | None] = mapped_column(
		JSONB,
		nullable=True,
		server_default="{}",
	)

	game: Mapped["Game"] = relationship(
		"Game",
		back_populates="party",
	)
	user: Mapped["User"] = relationship("User")
	character_sheets: Mapped[list["CharacterSheet"]] = relationship(
		"CharacterSheet",
		back_populates="party",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)
	dice_rolls: Mapped[list["DiceRoll"]] = relationship(
		"DiceRoll",
		back_populates="party",
		cascade="save-update, merge",
		passive_deletes=True,
		lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Party")

class Invite(Base):
	"""Приглашение с ограничением по времени и числу использований."""

	__tablename__ = "invites"

	token: Mapped[str] = mapped_column(
		String(64),
		primary_key=True,
		nullable=False,
	)
	game_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("games.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	creator_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	claimed_by: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	expires_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
	)
	uses_limit: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		server_default="1",
	)
	uses_current: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
		server_default="0",
	)
	message: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
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

	game: Mapped["Game"] = relationship(
		"Game",
		back_populates="invites",
	)
	creator: Mapped["User | None"] = relationship(
		"User",
		foreign_keys=[creator_id],
	)
	claimer: Mapped["User | None"] = relationship(
		"User",
		foreign_keys=[claimed_by],
	)

	@property
	def is_expired(self) -> bool:
		"""Сохранить прежнюю проверку времени и лимита использований."""
		now = datetime.now(timezone.utc)
		return (
				self.expires_at <= now
				or self.uses_current >= self.uses_limit
		)

	def consume(self) -> None:
		"""Увеличить счётчик, если приглашение ещё доступно.

		Сам метод не блокирует строку и не фиксирует транзакцию.
		"""
		if not self.is_expired:
			self.uses_current += 1

	def __repr__(self) -> str:
		"""Не раскрывать токен, включая первичный ключ из ORM."""
		return "<Invite(token=<hidden>)>"

class Session(Base):
	"""Отдельная игровая встреча внутри кампании."""

	__tablename__ = "sessions"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	game_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("games.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	title: Mapped[str | None] = mapped_column(
		String(255),
		nullable=True,
	)
	summary_log: Mapped[str | None] = mapped_column(
		Text,
		nullable=True,
	)
	start_time: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)
	end_time: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
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

	game: Mapped["Game"] = relationship(
		"Game",
		back_populates="sessions",
	)
	initiative: Mapped["InitiativeTracker | None"] = relationship(
		"InitiativeTracker",
		uselist=False,
		back_populates="session",
		cascade="all, delete-orphan",
	)
	chats: Mapped[list["Chat"]] = relationship(
		"Chat",
		back_populates="session",
		cascade="all, delete-orphan",
	)
	tokens: Mapped[list["Token"]] = relationship(
		"Token",
		back_populates="session",
		cascade="all, delete-orphan",
	)
	maps: Mapped[list["CampaignMap"]] = relationship(
		"CampaignMap",
		back_populates="session",
		cascade="save-update, merge",
		passive_deletes=True,
	)
	dice_rolls: Mapped[list["DiceRoll"]] = relationship(
		"DiceRoll",
		back_populates="session",
		cascade="save-update, merge",
		passive_deletes=True,
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="Session")

class InitiativeTracker(Base):
	"""Состояние очереди ходов одной игровой встречи."""

	__tablename__ = "initiative_tracker"

	session_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("sessions.id", ondelete="CASCADE"),
		primary_key=True,
	)
	turn_order_json: Mapped[list[dict]] = mapped_column(
		JSONB,
		nullable=False,
		server_default="[]",
	)
	current_index: Mapped[int] = mapped_column(
		Integer,
		default=0,
		nullable=False,
	)
	round_number: Mapped[int] = mapped_column(
		Integer,
		default=1,
		nullable=False,
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

	session: Mapped["Session"] = relationship(
		"Session",
		back_populates="initiative",
	)

	def __repr__(self) -> str:
		return _identity_repr(
			self,
			label="InitiativeTracker",
			field="session_id",
		)

class DiceRoll(Base):
	"""Сохранённый результат броска кубиков."""

	__tablename__ = "dice_rolls"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
		default=uuid4,
	)
	session_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("sessions.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	roller_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
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
	formula: Mapped[str] = mapped_column(
		String(100),
		nullable=False,
	)
	result_total: Mapped[int] = mapped_column(
		Integer,
		nullable=False,
	)
	individual_results: Mapped[list[int]] = mapped_column(
		ARRAY(Integer),
		nullable=False,
	)
	advantage: Mapped[str | None] = mapped_column(
		String(10),
		nullable=True,
	)
	is_gm_hidden: Mapped[bool] = mapped_column(
		Boolean,
		default=False,
		nullable=False,
	)
	context_type: Mapped[str | None] = mapped_column(
		String(50),
		nullable=True,
	)
	context_target_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		nullable=True,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=text("now()"),
	)

	session: Mapped["Session | None"] = relationship(
		"Session",
		back_populates="dice_rolls",
	)
	roller: Mapped["User | None"] = relationship(
		"User",
		back_populates="dice_rolls",
	)
	npc: Mapped["NPC | None"] = relationship(
		"NPC",
		back_populates="dice_rolls",
	)
	party: Mapped["Party | None"] = relationship(
		"Party",
		back_populates="dice_rolls",
	)
	def __repr__(self) -> str:
		return _identity_repr(self, label="DiceRoll")

class GameDeletionJob(Base):
	"""Данные для повторяемой очистки файлов удалённой игры.

	Внешнего ключа на games намеренно нет.
	"""

	__tablename__ = "game_deletion_jobs"

	game_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		primary_key=True,
	)
	master_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		nullable=False,
		index=True,
	)
	cleanup_plan: Mapped[dict] = mapped_column(
		JSONB,
		nullable=False,
	)
	cleanup_complete: Mapped[bool] = mapped_column(
		Boolean,
		nullable=False,
		default=False,
		server_default=text("false"),
		index=True,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		nullable=False,
		server_default=text("now()"),
	)

	def __repr__(self) -> str:
		return _identity_repr(
			self,
			label="GameDeletionJob",
			field="game_id",
		)