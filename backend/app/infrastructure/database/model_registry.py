# backend/app/infrastructure/database/model_registry.py

"""Явная загрузка и настройка ORM-моделей приложения.

Модуль не создаёт подключение к БД, не выполняет SQL
и не изменяет существующую схему.

Здесь перечислены только новые пути моделей.
Старый backend.app.Database._models не используется.
"""

from __future__ import annotations
from importlib import import_module
from sqlalchemy import MetaData, inspect
from sqlalchemy.orm import Mapper
from backend.app.infrastructure.database.base import Base


# Импорт каждого модуля регистрирует все его модели и таблицы связей.
# Имена классов нужны для обнаружения пустых или неполностью
# заполненных модулей во время переноса.
_MODEL_MODULES: tuple[tuple[str, tuple[str, ...]], ...] = (
	# Пользователи и аутентификация.
	(
		"backend.app.modules.users.models.user",
		("User",),
	),
	(
		"backend.app.modules.users.models.friendship",
		("Friendship",),
	),
	(
		"backend.app.modules.auth.models.mfa",
		("MFADevice",),
	),
	(
		"backend.app.modules.auth.models.oauth",
		("OAuthProvider",),
	),

	# Технические модели и администрирование.
	(
		"backend.app.infrastructure.database.models.system_event",
		("SystemEvent",),
	),
	(
		"backend.app.infrastructure.database.models.active_session_cache",
		("ActiveSessionCache",),
	),
	(
		"backend.app.modules.admin.models.audit_log",
		("AuditLog",),
	),
	(
		"backend.app.modules.admin.models.content_report",
		("ContentReport",),
	),

	# Игровые системы и движки правил.
	(
		"backend.app.modules.game_systems.models.game_systems",
		(
			"GameSystem",
			"HomebrewRule",
			"GameSystemRulesDraft",
			"GameSystemRulesVersion",
		),
	),
	(
		"backend.app.modules.game_systems.models.rule_engines",
		(
			"RuleEngine",
			"RuleEngineDraft",
			"RuleEngineVersion",
		),
	),

	# Игры и коммуникация.
	(
		"backend.app.modules.games.models.lobby",
		(
			"Game",
			"Party",
			"Invite",
			"Session",
			"InitiativeTracker",
			"DiceRoll",
			"GameDeletionJob",
		),
	),
	(
		"backend.app.modules.games.models.communication",
		("Chat", "Message"),
	),

	# Карты и персонажи.
	(
		"backend.app.modules.maps.models",
		(
			"CampaignMap",
			"MapLayer",
			"MapHex",
			"MapObject",
			"SpatialAudioZone",
			"Token",
		),
	),
	(
		"backend.app.modules.characters.models",
		(
			"Character",
			"CharacterSheet",
			"CharacterInventory",
			"CharacterSheetAbilityScore",
			"CharacterSheetSpell",
		),
	),

	# Каталог.
	(
		"backend.app.modules.catalog.models.character_building",
		(
			"Race",
			"CharacterClass",
			"Subclass",
			"Background",
			"Feat",
			"Origin",
		),
	),
	(
		"backend.app.modules.catalog.models.skills",
		(
			"Skill",
			"Characteristic",
			"SkillCharacteristicMap",
		),
	),
	(
		"backend.app.modules.catalog.models.equipment",
		(
			"Equipment",
			"ItemType",
			"Rarity",
			"Weapon",
			"WeaponType",
			"WeaponClass",
			"Armor",
			"ArmorType",
			"MagicalItem",
			"ItemEffect",
			"Artifact",
			"ArtifactProperty",
		),
	),
	(
		"backend.app.modules.catalog.models.magic",
		(
			"Spell",
			"SpellSlot",
			"MagicSchool",
			"Ability",
			"Effect",
			"DamageType",
			"SpellDamageType",
		),
	),
	(
		"backend.app.modules.catalog.models.worldbuilding",
		(
			"Language",
			"Creature",
			"CreatureSize",
			"CreatureType",
			"NPC",
			"NPCTag",
			"NpcTypeLink",
			"LoreEntry",
		),
	),

	# Медиа.
	(
		"backend.app.modules.media.models",
		("UploadedAsset", "AIGenerationJob"),
	),
)

def load_models() -> MetaData:
	"""Загрузить модели в единые metadata и registry.

	Повторный вызов использует обычный кеш импортов Python:
	повторного объявления классов и таблиц не происходит.

	Отсутствующий модуль или класс является ошибкой.
	Неполный реестр не возвращается как успешный результат.
	"""
	for module_path, model_names in _MODEL_MODULES:
		module = import_module(module_path)

		for model_name in model_names:
			model = getattr(module, model_name)
			mapper = inspect(model, raiseerr=False)

			if not isinstance(mapper, Mapper):
				raise TypeError(
					f"{module_path}.{model_name} "
					"не является ORM-моделью."
				)

			if (
					mapper.registry is not Base.registry
					or mapper.local_table.metadata is not Base.metadata
			):
				raise RuntimeError(
					f"{module_path}.{model_name} "
					"использует другой Base или MetaData."
				)

	return Base.metadata

def configure_models() -> MetaData:
	"""Загрузить модели, разрешить внешние ключи и настроить связи.

	Проверяет определения Python-моделей без подключения к БД.
	Не проверяет существующую схему PostgreSQL и поведение сервисов.
	"""
	metadata = load_models()

	# Обращение к column заставляет SQLAlchemy разрешить ссылку.
	# Если целевой таблицы или столбца нет, исключение не скрывается.
	for table in metadata.tables.values():
		for foreign_key in table.foreign_keys:
			_ = foreign_key.column

	# Настраиваем только реестр нового Base, а не все реестры,
	# которые могли быть загружены в текущий процесс.
	Base.registry.configure()

	return metadata

__all__ = ["load_models", "configure_models"]