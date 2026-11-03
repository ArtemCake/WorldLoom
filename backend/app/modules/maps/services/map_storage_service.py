# backend/app/modules/maps/services/map_storage_service.py

"""Назначение номеров и относительных адресов изображений карт.

Файловые операции не выполняются.
Commit и rollback остаются за вызывающим слоем.

Порядок блокировок: игра, затем пользователь.
Для операции над несколькими играми вызывающий слой сначала
блокирует все затрагиваемые игры в порядке их идентификаторов.
"""

from __future__ import annotations
import re
from typing import Protocol
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.games.models.lobby import Game
from backend.app.modules.maps.errors import InvalidMapStorage, MapStorageConflict, MapStorageForbidden, MapStorageNotFound
from backend.app.modules.users.models.user import User


_USERS = User.__table__
_MAX_COUNTER = 2_147_483_647

class MapImageSource(Protocol):
	id: UUID
	background_storage_path: str | None

def _folder_name(prefix: str, label: str, entity_id: UUID) -> str:
	slug = re.sub(r"[^\w-]+", "-", (label or "").strip().lower()).strip("-_")[:40].rstrip("-_")
	return f"{prefix}-{slug or 'unnamed'}-{entity_id}"

def _checked_folder(value: str, prefix: str, entity_id: UUID) -> str:
	if not isinstance(value, str) or not re.fullmatch(rf"{prefix}-[\w-]+", value) or not value.endswith(f"-{entity_id}"):
		raise MapStorageConflict("Сохранённый каталог не соответствует владельцу или игре")

	return value

def _checked_number(value: int, label: str) -> int:
	if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_COUNTER:
		raise MapStorageConflict(f"Некорректное значение: {label}")

	return value

async def allocate_location(session: AsyncSession, game_id: UUID, master_id: UUID, *, number: int | None = None) -> tuple[int, str]:
	"""Назначить номер и адрес без фиксации транзакции.

	number передаётся только доверенной операцией переноса старой карты.
	Проверка уникальности такого номера остаётся обязанностью этой
	операции и ограничений БД.

	flush сохраняет ожидающие ORM-изменения всей текущей сессии,
	как и в исходном сервисе.
	"""
	if not isinstance(game_id, UUID) or not isinstance(master_id, UUID):
		raise InvalidMapStorage("Требуются UUID игры и проверенного пользователя")

	if number is not None:
		_checked_number(number, "номер карты")

	result = await session.execute(
		select(Game)
		.where(Game.id == game_id)
		.with_for_update(of=Game)
		.execution_options(populate_existing=True)
	)
	game = result.scalar_one_or_none()

	if game is None:
		raise MapStorageNotFound("Игра не найдена")

	if game.master_id != master_id:
		raise MapStorageForbidden("Только мастер игры может сохранять её карты")

	result = await session.execute(
		select(_USERS.c.id, _USERS.c.nickname, _USERS.c.maps_storage_folder)
		.where(_USERS.c.id == master_id)
		.with_for_update()
	)
	master = result.one_or_none()

	if master is None:
		raise MapStorageNotFound("Мастер игры не найден")

	master_folder = master.maps_storage_folder or _folder_name("master", master.nickname, master.id)
	game_folder = game.maps_storage_folder or _folder_name("game", game.title, game.id)
	_checked_folder(master_folder, "master", master_id)
	_checked_folder(game_folder, "game", game_id)

	next_number = _checked_number(game.next_map_number, "счётчик карт игры")
	assigned_number = next_number if number is None else number
	updated_counter = max(next_number, assigned_number + 1)

	if updated_counter > _MAX_COUNTER:
		raise MapStorageConflict("Исчерпан диапазон номеров карт игры")

	if not master.maps_storage_folder:
		await session.execute(
			update(_USERS)
			.where(_USERS.c.id == master_id)
			.values(maps_storage_folder=master_folder)
		)

	game.maps_storage_folder = game_folder
	game.next_map_number = updated_counter
	await session.flush()

	return assigned_number, f"{master_folder}/{game_folder}/map-{assigned_number}.png"

def image_key(campaign_map: MapImageSource) -> UUID | str:
	"""Вернуть новый относительный адрес либо UUID старого изображения."""
	return campaign_map.background_storage_path or campaign_map.id