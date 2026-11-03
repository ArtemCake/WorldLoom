# backend/app/modules/maps/services/map_management_service.py

"""Доступ к картам и операции управления внутри текущей транзакции.

Порядок блокировок: затрагиваемые игры по Game.id, затем карта.
Вызывающая операция получает блокировки до изменения объектов.

Commit, rollback и обработка отмены принадлежат вызывающему слою.
Этот модуль не выполняет файловые операции и не подключает API.
"""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid4
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.storage.local_storage import FileReplacement, LocalStorage
from backend.app.modules.games.models.lobby import Game, Session as GameSession
from backend.app.modules.maps.errors import InvalidMapOperation, MapAccessDenied, MapCommitOutcomeUnknown, MapEntityNotFound
from backend.app.modules.maps.errors import MapImageStorageFailure, MapMoveBlocked, MapStateConflict
from backend.app.modules.maps.models import CampaignMap, MapHex, MapLayer, MapObject, SpatialAudioZone, Token, MapDeletionJob
from backend.app.modules.maps.services import map_image_service as images
from backend.app.modules.maps.services import map_storage_service as storage
from backend.app.modules.maps.schemas import MapCreate, MapGridSettings, MapUpdate
from backend.app.modules.maps.services import map_hex_service as hexes
from backend.app.modules.maps.services import map_cleanup_service as cleanup


log = logging.getLogger(__name__)
T = TypeVar("T")

def _require_uuid(value: UUID, label: str) -> None:
	if not isinstance(value, UUID):
		raise InvalidMapOperation(f"{label}: требуется UUID")

async def list_target_games(session: AsyncSession, master_id: UUID, source_game_id: UUID) -> list[Game]:
	"""Получить игры мастера, исключая исходную; не выдаёт разрешение на перенос."""
	_require_uuid(master_id, "Мастер")
	_require_uuid(source_game_id, "Исходная игра")

	statement = (
		select(Game)
		.where(Game.master_id == master_id, Game.id != source_game_id)
		.order_by(Game.title, Game.id)
	)
	result = await session.execute(statement)
	return list(result.scalars().all())

@dataclass(frozen=True)
class MapTransferContext:
	source: CampaignMap
	target_game_id: UUID
	map_number: int
	storage_path: str

async def _lock_games(session: AsyncSession, map_id: UUID, master_id: UUID, *, target_game_id: UUID | None = None, expected_game_id: UUID | None = None) -> UUID:
	"""Проверить аргументы, прочитать принадлежность и заблокировать игры."""
	_require_uuid(map_id, "Карта")
	_require_uuid(master_id, "Мастер")

	if target_game_id is not None:
		_require_uuid(target_game_id, "Целевая игра")

	if expected_game_id is not None:
		_require_uuid(expected_game_id, "Ожидаемая исходная игра")

	source_statement = select(CampaignMap.game_id).where(CampaignMap.id == map_id)
	source_game_id = (await session.execute(source_statement)).scalar_one_or_none()

	if source_game_id is None:
		raise MapEntityNotFound("Карта не найдена")

	if expected_game_id is not None and source_game_id != expected_game_id:
		raise MapStateConflict("Карта уже находится в другой игре. Обновите страницу")

	if target_game_id == source_game_id:
		raise InvalidMapOperation("Выберите другую игру")

	game_ids = {source_game_id}

	if target_game_id is not None:
		game_ids.add(target_game_id)

	games_statement = (
		select(Game)
		.where(Game.id.in_(game_ids))
		.order_by(Game.id)
		.with_for_update()
		.execution_options(populate_existing=True)
	)
	result = await session.execute(games_statement)
	games = {game.id: game for game in result.scalars().all()}

	for game_id in sorted(game_ids):
		game = games.get(game_id)

		if game is None:
			raise MapEntityNotFound("Игра не найдена")

		if game.master_id != master_id:
			raise MapAccessDenied("Для операции нужны права мастера во всех затрагиваемых играх")

	return source_game_id

async def _lock_map(session: AsyncSession, map_id: UUID, source_game_id: UUID) -> CampaignMap:
	"""Заблокировать карту после игр и повторно проверить принадлежность."""
	map_statement = (
		select(CampaignMap)
		.where(CampaignMap.id == map_id)
		.with_for_update()
		.execution_options(populate_existing=True)
	)
	campaign_map = (await session.execute(map_statement)).scalar_one_or_none()

	if campaign_map is None:
		raise MapEntityNotFound("Карта не найдена")

	if campaign_map.game_id != source_game_id:
		raise MapStateConflict("Принадлежность карты изменилась. Обновите страницу")

	return campaign_map

async def lock_context(session: AsyncSession, map_id: UUID, master_id: UUID, *, target_game_id: UUID | None = None, expected_game_id: UUID | None = None) -> CampaignMap:
	"""Заблокировать игры и карту для операции без назначения нового адреса."""
	source_game_id = await _lock_games(
		session, map_id, master_id, target_game_id=target_game_id, expected_game_id=expected_game_id,
	)
	return await _lock_map(session, map_id, source_game_id)

async def prepare_transfer_context(session: AsyncSession, map_id: UUID, master_id: UUID, source_game_id: UUID, target_game_id: UUID) -> MapTransferContext:
	"""Назначить адрес до блокировки карты внутри текущей транзакции."""
	_require_uuid(source_game_id, "Исходная игра")
	_require_uuid(target_game_id, "Целевая игра")

	actual_source_id = await _lock_games(
		session, map_id, master_id, target_game_id=target_game_id, expected_game_id=source_game_id,
	)
	number, path = await storage.allocate_location(session, target_game_id, master_id)
	campaign_map = await _lock_map(session, map_id, actual_source_id)
	return MapTransferContext(campaign_map, target_game_id, number, path)

async def set_map_activity(session: AsyncSession, map_id: UUID, master_id: UUID, *, active: bool) -> CampaignMap:
	"""Изменить активность карты без завершения текущей транзакции."""
	if not isinstance(active, bool):
		raise InvalidMapOperation("Активность карты должна быть логическим значением")

	campaign_map = await lock_context(session, map_id, master_id)

	if active:
		statement = (
			update(CampaignMap)
			.where(
				CampaignMap.game_id == campaign_map.game_id,
				CampaignMap.id != map_id,
				CampaignMap.is_active_in_session.is_(True),
				)
			.values(is_active_in_session=False)
			.execution_options(synchronize_session="fetch")
		)
		await session.execute(statement)

	campaign_map.is_active_in_session = active
	await session.flush()
	return campaign_map

async def check_move_dependencies(session: AsyncSession, map_id: UUID) -> None:
	"""Проверить препятствия переносу после получения общего контекста блокировок."""
	_require_uuid(map_id, "Карта")
	layer_ids = select(MapLayer.id).where(MapLayer.map_id == map_id)
	hex_ids = select(MapHex.id).where(MapHex.layer_id.in_(layer_ids))
	token_statement = (
		select(Token.id)
		.where(or_(Token.current_map_id == map_id, Token.current_hex_id.in_(hex_ids)))
		.limit(1)
	)
	token_id = (await session.execute(token_statement)).scalar_one_or_none()

	if token_id is not None:
		raise MapMoveBlocked(
			"Перенос невозможен: к карте или её гексам привязаны токены. "
			"Сначала снимите привязки либо воспользуйтесь копированием"
		)

	object_statement = select(MapObject.id).where(MapObject.layer_id.in_(layer_ids)).limit(1)
	object_id = (await session.execute(object_statement)).scalar_one_or_none()

	if object_id is not None:
		raise MapMoveBlocked(
			"Перенос карты с объектами пока не поддерживается. "
			"Объекты не удалены. Можно скопировать основу карты"
		)

	audio_statement = select(SpatialAudioZone.id).where(SpatialAudioZone.map_id == map_id).limit(1)
	audio_id = (await session.execute(audio_statement)).scalar_one_or_none()

	if audio_id is not None:
		raise MapMoveBlocked(
			"Перенос карты с аудиозонами пока не поддерживается. "
			"Аудиозоны не удалены. Можно скопировать основу карты"
		)

async def copy_layers(session: AsyncSession, source_map_id: UUID, destination: CampaignMap) -> None:
	"""Скопировать слои и гексы в уже добавленную карту без завершения транзакции."""
	_require_uuid(source_map_id, "Исходная карта")
	_require_uuid(destination.id, "Карта назначения")

	if destination.id == source_map_id:
		raise InvalidMapOperation("Нельзя копировать слои карты в неё же")

	if not isinstance(destination.fog_of_war_enabled, bool):
		raise InvalidMapOperation("Настройка тумана войны должна быть логическим значением")

	layers_statement = (
		select(MapLayer)
		.where(MapLayer.map_id == source_map_id)
		.order_by(MapLayer.z_index, MapLayer.id)
	)
	layers = list((await session.execute(layers_statement)).scalars().all())

	for source_layer in layers:
		layer = MapLayer(
			id=uuid4(),
			map_id=destination.id,
			name=source_layer.name,
			z_index=source_layer.z_index,
			opacity=source_layer.opacity,
			is_visible=source_layer.is_visible,
			layer_type=source_layer.layer_type,
			data_json=deepcopy(source_layer.data_json),
		)
		session.add(layer)
		await session.flush()

		hexes_statement = select(MapHex).where(MapHex.layer_id == source_layer.id).order_by(MapHex.id)
		hexes = list((await session.execute(hexes_statement)).scalars().all())

		for start in range(0, len(hexes), 500):
			copies = [
				MapHex(
					id=uuid4(),
					layer_id=layer.id,
					axial_q=source_hex.axial_q,
					axial_r=source_hex.axial_r,
					h3_index=source_hex.h3_index,
					terrain_type_id=source_hex.terrain_type_id,
					elevation=source_hex.elevation,
					is_visible_to_players=not destination.fog_of_war_enabled,
					explored_by_players=False,
					data_json=deepcopy(source_hex.data_json),
				)
				for source_hex in hexes[start:start + 500]
			]
			session.add_all(copies)
			await session.flush()

@dataclass
class _TransferFiles:
	new_key: str | None = None
	old_key: UUID | str | None = None
	created: bool = False

async def _wait_transfer_task(task: asyncio.Task[T]) -> tuple[T, bool]:
	"""Дождаться отдельной задачи, запомнив отмену вызывающей операции."""
	cancelled = False

	while True:
		try:
			return await asyncio.shield(task), cancelled
		except asyncio.CancelledError:
			if task.cancelled():
				raise

			cancelled = True

async def _cleanup_transfer_file(image_key: UUID | str, *, root: Path) -> None:
	"""Попытаться удалить файл, записав неудачу для последующей проверки."""
	try:
		path = images.image_path(image_key, root=root)
		await asyncio.to_thread(lambda: LocalStorage(root).remove_file(path))
	except Exception:
		log.exception("Не удалось очистить файл операции переноса карты: %s", image_key)

async def _rollback_transfer(session: AsyncSession) -> None:
	"""Попытаться откатить сессию, не подменяя исходную ошибку операции."""
	try:
		await session.rollback()
	except Exception:
		log.exception("Откат операции с картой завершился ошибкой; сессию нельзя использовать повторно")

async def _abort_transfer(session: AsyncSession, files: _TransferFiles, *, root: Path) -> None:
	"""До commit очистить собственный файл, затем попытаться откатить БД."""
	try:
		if files.created and files.new_key is not None:
			await _cleanup_transfer_file(files.new_key, root=root)
	finally:
		await _rollback_transfer(session)

async def _prepare_transfer_image(source: CampaignMap, files: _TransferFiles, *, root: Path, copying: bool) -> bytes | None:
	"""Прочитать серверный фон; при копировании отклонить произвольный URL."""
	background_url = source.background_image_url
	local_url = f"/maps/{source.id}/background"

	if background_url != local_url:
		if copying and background_url:
			raise MapStateConflict(
				"Карта использует фон по произвольному адресу. "
				"Сначала загрузите изображение через редактирование карты"
			)

		return None

	files.old_key = storage.image_key(source)

	if files.old_key == files.new_key:
		raise MapStateConflict("Исходное и целевое изображения не должны иметь одинаковый адрес")

	return await images.read_background(files.old_key, root=root)

async def _write_transfer_image(files: _TransferFiles, contents: bytes, *, root: Path, verify: bool) -> None:
	"""Записать новый файл и зафиксировать владение до передачи отмены."""
	if files.new_key is None:
		raise InvalidMapOperation("Не назначен адрес изображения карты")

	task = asyncio.create_task(images.save_background(files.new_key, contents, root=root))
	_, cancelled = await _wait_transfer_task(task)
	files.created = True

	if cancelled:
		raise asyncio.CancelledError()

	if verify:
		written = await images.read_background(files.new_key, root=root)

		if written != contents:
			raise MapImageStorageFailure("Не удалось проверить изображение после переноса")

def _make_map_copy(context: MapTransferContext, *, with_background: bool) -> CampaignMap:
	source = context.source
	new_map_id = uuid4()
	return CampaignMap(
		id=new_map_id,
		game_id=context.target_game_id,
		session_id=None,
		map_number=context.map_number,
		background_storage_path=context.storage_path,
		title=source.title,
		map_type=source.map_type,
		background_image_url=f"/maps/{new_map_id}/background" if with_background else None,
		grid_settings_json=deepcopy(source.grid_settings_json),
		fog_of_war_enabled=source.fog_of_war_enabled,
		lighting_model=source.lighting_model,
		is_active_in_session=False,
	)

async def _commit_transfer(session: AsyncSession, files: _TransferFiles, *, root: Path, copying: bool) -> bool:
	"""Отделить подтверждённый commit от ошибки с неизвестным результатом."""
	try:
		task = asyncio.create_task(session.commit())
		_, cancelled = await _wait_transfer_task(task)
	except BaseException as exc:
		log.exception(
			"Результат commit операции с картой не подтверждён. Новый файл сохранён: %s; прежний файл: %s",
			files.new_key if files.created else None,
			files.old_key,
		)
		await _wait_transfer_task(asyncio.create_task(_rollback_transfer(session)))

		if not isinstance(exc, Exception):
			raise

		raise MapCommitOutcomeUnknown(
			"Не удалось подтвердить сохранение операции. "
			"Проверьте состояние карты перед повтором; изображения сохранены"
		) from exc

	if not copying and files.created and files.old_key is not None:
		cleanup = asyncio.create_task(_cleanup_transfer_file(files.old_key, root=root))
		_, cleanup_cancelled = await _wait_transfer_task(cleanup)
		cancelled = cancelled or cleanup_cancelled

	return cancelled

async def _transfer_map(session: AsyncSession, map_id: UUID, master_id: UUID, source_game_id: UUID, target_game_id: UUID, *, root: Path, copying: bool) -> CampaignMap:
	"""Выполнить отдельную операцию копирования или перемещения карты."""
	files = _TransferFiles()

	try:
		context = await prepare_transfer_context(session, map_id, master_id, source_game_id, target_game_id)
		files.new_key = context.storage_path
		source = context.source

		if not copying:
			await check_move_dependencies(session, source.id)

		contents = await _prepare_transfer_image(source, files, root=root, copying=copying)

		if contents is not None:
			await _write_transfer_image(files, contents, root=root, verify=not copying)

		if copying:
			result = _make_map_copy(context, with_background=contents is not None)
			session.add(result)
			await session.flush()
			await copy_layers(session, source.id, result)
		else:
			result = source
			result.game_id = context.target_game_id
			result.map_number = context.map_number
			result.background_storage_path = context.storage_path
			result.session_id = None
			result.is_active_in_session = False

		await session.flush()

	except BaseException:
		abort = asyncio.create_task(_abort_transfer(session, files, root=root))
		await _wait_transfer_task(abort)
		raise

	cancelled = await _commit_transfer(session, files, root=root, copying=copying)

	if cancelled:
		raise asyncio.CancelledError()

	await session.refresh(result)
	return result

async def copy_map(session: AsyncSession, map_id: UUID, master_id: UUID, source_game_id: UUID, target_game_id: UUID, *, root: Path) -> CampaignMap:
	"""Скопировать основу карты в другую игру и завершить транзакцию."""
	return await _transfer_map(session, map_id, master_id, source_game_id, target_game_id, root=root, copying=True)

async def move_map(session: AsyncSession, map_id: UUID, master_id: UUID, source_game_id: UUID, target_game_id: UUID, *, root: Path) -> CampaignMap:
	"""Переместить карту без запрещённых зависимостей и завершить транзакцию."""
	return await _transfer_map(session, map_id, master_id, source_game_id, target_game_id, root=root, copying=False)

def _prepare_map_creation(data: MapCreate) -> tuple[dict, MapGridSettings]:
	"""Подготовить независимые значения без изменения входной модели."""
	if not isinstance(data, MapCreate):
		raise InvalidMapOperation("Для создания карты требуется MapCreate")

	title = data.title.strip()

	if not title:
		raise InvalidMapOperation("Укажите название карты")

	if data.map_type == "procedural_generation":
		raise InvalidMapOperation("Создание процедурных карт пока не подключено. Используйте карту на основе изображения")

	if data.map_type != "image_upload":
		raise InvalidMapOperation("Неизвестный тип карты")

	settings = MapGridSettings.model_validate(data.grid_settings_json or {})
	values = data.model_dump()
	values["title"] = title
	values["grid_settings_json"] = {
		**deepcopy(data.grid_settings_json or {}),
		**settings.model_dump(),
		"orientation": "pointy-top",
		"offset": "odd-r",
	}
	values["is_active_in_session"] = False
	return values, settings

async def _check_creation_session(session: AsyncSession, game_id: UUID, session_id: UUID | None) -> None:
	"""После проверки прав на игру проверить принадлежность встречи."""
	if session_id is None:
		return

	statement = select(GameSession.game_id).where(GameSession.id == session_id)
	actual_game_id = (await session.execute(statement)).scalar_one_or_none()

	if actual_game_id is None:
		raise MapEntityNotFound("Игровая сессия не найдена")

	if actual_game_id != game_id:
		raise InvalidMapOperation("Сессия не принадлежит указанной игре")

async def create_map(session: AsyncSession, master_id: UUID, data: MapCreate, *, root: Path, limits: images.ImageLimits,
		background_image: images.BackgroundUpload | None = None) -> CampaignMap:
	"""Создать карту, начальную сетку и при необходимости изображение."""
	files = _TransferFiles()

	try:
		_require_uuid(master_id, "Мастер")
		values, grid_settings = _prepare_map_creation(data)
		contents = None

		if background_image is not None:
			contents = await images.prepare_background(background_image, limits=limits)

		number, path = await storage.allocate_location(session, data.game_id, master_id)
		files.new_key = path
		await _check_creation_session(session, data.game_id, data.session_id)
		map_id = uuid4()
		values["map_number"] = number
		values["background_storage_path"] = path

		if contents is not None:
			await _write_transfer_image(files, contents, root=root, verify=False)
			values["background_image_url"] = f"/maps/{map_id}/background"

		campaign_map = CampaignMap(id=map_id, **values)
		session.add(campaign_map)
		await session.flush()

		if grid_settings.show_grid or data.fog_of_war_enabled:
			await hexes.add_hex_grid(session, campaign_map, grid_settings.rows, grid_settings.cols)

		await session.flush()

	except BaseException:
		abort = asyncio.create_task(_abort_transfer(session, files, root=root))
		await _wait_transfer_task(abort)
		raise

	cancelled = await _commit_transfer(session, files, root=root, copying=True)

	if cancelled:
		raise asyncio.CancelledError()

	await session.refresh(campaign_map)
	return campaign_map

@dataclass
class _MapUpdateFiles:
	replacement: FileReplacement | None = None
	previous_key: UUID | str | None = None
	replacement_key: UUID | str | None = None

def _prepare_map_update(data: MapUpdate) -> dict:
	"""Получить только переданные поля без изменения входной модели."""
	if not isinstance(data, MapUpdate):
		raise InvalidMapOperation("Для изменения карты требуется MapUpdate")

	values = deepcopy(data.model_dump(exclude_unset=True))

	if "title" in values:
		title = values["title"]

		if title is None or not title.strip():
			raise InvalidMapOperation("Укажите название карты")

		values["title"] = title.strip()

	return values

async def _prepare_map_update_context(session: AsyncSession, map_id: UUID, master_id: UUID, *, with_image: bool) -> tuple[CampaignMap, tuple[int, str] | None]:
	"""Подготовить назначение адреса до блокировки карты, но не менять её."""
	source_game_id = await _lock_games(session, map_id, master_id)

	if not with_image:
		return await _lock_map(session, map_id, source_game_id), None

	statement = select(CampaignMap.map_number, CampaignMap.background_storage_path).where(CampaignMap.id == map_id)
	snapshot = (await session.execute(statement)).one_or_none()

	if snapshot is None:
		raise MapEntityNotFound("Карта не найдена")

	previous_number, previous_path = snapshot
	allocated = None

	if not previous_path:
		allocated = await storage.allocate_location(session, source_game_id, master_id, number=previous_number)

	campaign_map = await _lock_map(session, map_id, source_game_id)

	if campaign_map.map_number != previous_number or campaign_map.background_storage_path != previous_path:
		raise MapStateConflict("Адрес карты изменился. Обновите страницу")

	if campaign_map.map_type != "image_upload":
		raise InvalidMapOperation("Загрузка фона доступна только для карты на основе изображения")

	return campaign_map, allocated

async def _replace_map_update_image(files: _MapUpdateFiles, contents: bytes, *, root: Path) -> None:
	"""Дождаться замены и сохранить объект компенсации до передачи отмены."""
	if files.replacement_key is None:
		raise InvalidMapOperation("Не назначен адрес изображения карты")

	task = asyncio.create_task(images.replace_background(files.replacement_key, contents, root=root))
	replacement, cancelled = await _wait_transfer_task(task)
	files.replacement = replacement

	if cancelled:
		raise asyncio.CancelledError()

async def _abort_map_update(session: AsyncSession, files: _MapUpdateFiles, *, root: Path) -> None:
	"""До commit восстановить файл и в любом случае попытаться откатить БД."""
	try:
		if files.replacement is not None:
			await images.rollback_background(files.replacement, root=root)
	except Exception:
		log.exception("Не удалось восстановить фон карты; требуется проверка хранилища")
		raise
	finally:
		await _rollback_transfer(session)

async def _finish_map_update(files: _MapUpdateFiles, *, root: Path) -> None:
	"""После commit завершить замену и очистить прежний отдельный файл."""
	if files.replacement is None:
		return

	try:
		await images.finish_background_replacement(files.replacement, root=root)

		if files.previous_key is not None and files.previous_key != files.replacement_key:
			await _cleanup_transfer_file(files.previous_key, root=root)
	except Exception:
		log.exception("Карта сохранена, но завершение файловой замены требует проверки")

async def update_map(session: AsyncSession, map_id: UUID, master_id: UUID, data: MapUpdate, *, root: Path, limits: images.ImageLimits,
		background_image: images.BackgroundUpload | None = None) -> CampaignMap:
	"""Изменить карту и завершить отдельную транзакцию операции."""
	files = _MapUpdateFiles()

	try:
		values = _prepare_map_update(data)
		campaign_map, allocated = await _prepare_map_update_context(session, map_id, master_id, with_image=background_image is not None)

		if background_image is not None:
			contents = await images.prepare_background(background_image, limits=limits)
			files.previous_key = storage.image_key(campaign_map)

			if allocated is not None:
				campaign_map.map_number, campaign_map.background_storage_path = allocated

			files.replacement_key = storage.image_key(campaign_map)
			await _replace_map_update_image(files, contents, root=root)
			values["background_image_url"] = f"/maps/{map_id}/background"

		for field, value in values.items():
			setattr(campaign_map, field, value)

		await session.flush()

	except BaseException:
		abort = asyncio.create_task(_abort_map_update(session, files, root=root))
		await _wait_transfer_task(abort)
		raise

	try:
		cancelled = await _commit_transfer(session, _TransferFiles(), root=root, copying=True)
	except BaseException:
		if files.replacement is not None:
			log.exception(
				"Результат сохранения карты не подтверждён; новый фон и резервная копия оставлены: %s; %s",
				files.replacement.target,
				files.replacement.backup,
			)

		raise

	finish = asyncio.create_task(_finish_map_update(files, root=root))
	_, finish_cancelled = await _wait_transfer_task(finish)

	if cancelled or finish_cancelled:
		raise asyncio.CancelledError()

	await session.refresh(campaign_map)
	return campaign_map

async def generate_hex_grid(session: AsyncSession, map_id: UUID, master_id: UUID, rows: int, cols: int) -> MapLayer:
	"""Добавить сетку на существующую карту и завершить транзакцию."""
	try:
		_require_uuid(map_id, "Карта")
		_require_uuid(master_id, "Мастер")

		for label, value in (("Количество строк", rows), ("Количество столбцов", cols)):
			if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 200:
				raise InvalidMapOperation(f"{label} должно быть целым числом от 1 до 200")

		game_id = await _lock_games(session, map_id, master_id)
		campaign_map = await _lock_map(session, map_id, game_id)
		statement = (
			select(MapLayer.id)
			.where(MapLayer.map_id == map_id, MapLayer.layer_type == "vector_tiles")
			.limit(1)
		)
		existing = (await session.execute(statement)).scalar_one_or_none()

		if existing is not None:
			raise MapStateConflict("На этой карте уже есть слой гексов")

		layer = await hexes.add_hex_grid(session, campaign_map, rows, cols)
		await session.flush()

	except BaseException:
		await _wait_transfer_task(asyncio.create_task(_rollback_transfer(session)))
		raise

	try:
		_, cancelled = await _wait_transfer_task(asyncio.create_task(session.commit()))
	except BaseException as exc:
		log.exception("Не удалось подтвердить фиксацию создания сетки карты %s", map_id)
		await _wait_transfer_task(asyncio.create_task(_rollback_transfer(session)))

		if not isinstance(exc, Exception):
			raise

		raise MapCommitOutcomeUnknown(
			"Не удалось подтвердить создание сетки. Проверьте состояние карты перед повтором"
		) from exc

	if cancelled:
		raise asyncio.CancelledError()

	await session.refresh(layer)
	return layer

async def require_maps_master(session: AsyncSession, game_id: UUID, master_id: UUID) -> Game:
	"""Проверить права на каталог и удерживать игру до завершения транзакции."""
	_require_uuid(game_id, "Игра")
	_require_uuid(master_id, "Мастер")

	statement = (
		select(Game)
		.where(Game.id == game_id)
		.with_for_update(read=True)
		.execution_options(populate_existing=True)
	)
	game = (await session.execute(statement)).scalar_one_or_none()

	if game is None:
		raise MapEntityNotFound("Игра не найдена")

	if game.master_id != master_id:
		raise MapAccessDenied("Каталог карт доступен только мастеру игры")

	return game

async def list_maps_for_game(session: AsyncSession, game_id: UUID, master_id: UUID) -> list[CampaignMap]:
	"""Получить каталог карт только после проверки прав мастера."""
	await require_maps_master(session, game_id, master_id)

	statement = (
		select(CampaignMap)
		.where(CampaignMap.game_id == game_id)
		.order_by(CampaignMap.title, CampaignMap.id)
		.execution_options(populate_existing=True)
	)
	result = await session.execute(statement)
	return list(result.scalars().all())

async def get_map(session: AsyncSession, map_id: UUID, master_id: UUID) -> CampaignMap:
	"""Получить карту мастера с блокировками игры и карты."""
	_require_uuid(map_id, "Карта")
	_require_uuid(master_id, "Мастер")
	return await lock_context(session, map_id, master_id)

async def read_map_background(session: AsyncSession, map_id: UUID, master_id: UUID, *, root: Path) -> bytes:
	"""Прочитать серверный фон после получения блокировок и проверки доступа."""
	campaign_map = await get_map(session, map_id, master_id)
	image_key = storage.image_key(campaign_map)
	return await images.read_background(image_key, root=root)

async def recalc_fog_of_war(session: AsyncSession, map_id: UUID, master_id: UUID, viewer_token_ids: list[UUID]) -> set[UUID]:
	"""Пересчитать видимость под блокировками и завершить отдельную транзакцию."""
	try:
		_require_uuid(map_id, "Карта")
		_require_uuid(master_id, "Мастер")

		if not isinstance(viewer_token_ids, list):
			raise InvalidMapOperation("Наблюдатели должны быть переданы списком UUID")

		for token_id in viewer_token_ids:
			_require_uuid(token_id, "Наблюдатель")

		campaign_map = await lock_context(session, map_id, master_id)
		visible_ids = await hexes.recalculate_visibility(session, campaign_map, list(dict.fromkeys(viewer_token_ids)))
		await session.flush()

	except BaseException:
		await _wait_transfer_task(asyncio.create_task(_rollback_transfer(session)))
		raise

	try:
		_, cancelled = await _wait_transfer_task(asyncio.create_task(session.commit()))
	except BaseException as exc:
		log.exception("Не удалось подтвердить фиксацию видимости карты %s", map_id)
		await _wait_transfer_task(asyncio.create_task(_rollback_transfer(session)))

		if not isinstance(exc, Exception):
			raise

		raise MapCommitOutcomeUnknown(
			"Не удалось подтвердить сохранение видимости. Проверьте состояние карты перед повтором"
		) from exc

	if cancelled:
		raise asyncio.CancelledError()

	return visible_ids

async def _get_map_deletion_job(session: AsyncSession, map_id: UUID, master_id: UUID) -> MapDeletionJob | None:
	"""Получить и заблокировать задание, проверив владельца."""
	statement = (
		select(MapDeletionJob)
		.where(MapDeletionJob.map_id == map_id)
		.with_for_update()
		.execution_options(populate_existing=True)
	)
	job = (await session.execute(statement)).scalar_one_or_none()

	if job is None:
		return None

	if job.master_id != master_id:
		raise MapAccessDenied("Очистка карты доступна только владельцу задания")

	if not isinstance(job.cleanup_complete, bool):
		raise MapStateConflict("Состояние задания очистки имеет неподдерживаемый формат")

	return job

async def _require_deleted_map(session: AsyncSession, map_id: UUID) -> None:
	statement = select(CampaignMap.id).where(CampaignMap.id == map_id)
	existing = (await session.execute(statement)).scalar_one_or_none()

	if existing is not None:
		raise MapStateConflict("Карта ещё существует. Очистка её файлов запрещена")

async def _require_unshared_map_background(session: AsyncSession, background_storage_path: str | None, *, excluding_map_id: UUID | None = None) -> None:
	"""Не разрешать удаление файла, на который ссылается другая сохранённая карта."""
	if background_storage_path is None:
		return

	statement = select(CampaignMap.id).where(CampaignMap.background_storage_path == background_storage_path)

	if excluding_map_id is not None:
		statement = statement.where(CampaignMap.id != excluding_map_id)

	existing = (await session.execute(statement.limit(1))).scalar_one_or_none()

	if existing is not None:
		raise MapStateConflict("На файл фона ссылается другая карта. Требуется проверить адреса хранения")

async def stage_map_deletion(session: AsyncSession, map_id: UUID, master_id: UUID, *, root: Path) -> MapDeletionJob:
	"""Подготовить удаление карты и задание очистки без завершения транзакции."""
	_require_uuid(map_id, "Карта")
	_require_uuid(master_id, "Мастер")
	job = await _get_map_deletion_job(session, map_id, master_id)

	if job is not None:
		await _require_deleted_map(session, map_id)
		return job

	campaign_map = await lock_context(session, map_id, master_id)
	background_storage_path = campaign_map.background_storage_path or None
	plan = cleanup.build_map_cleanup_plan(map_id, campaign_map.game_id, master_id, background_storage_path, root=root)
	await _require_unshared_map_background(session, background_storage_path, excluding_map_id=map_id)

	job = MapDeletionJob(
		map_id=map_id,
		game_id=campaign_map.game_id,
		master_id=master_id,
		cleanup_plan=plan,
		cleanup_complete=False,
	)
	session.add(job)

	hex_ids = (
		select(MapHex.id)
		.join(MapLayer, MapHex.layer_id == MapLayer.id)
		.where(MapLayer.map_id == map_id)
	)
	statement = (
		update(Token)
		.where(or_(Token.current_map_id == map_id, Token.current_hex_id.in_(hex_ids)))
		.values(current_map_id=None, current_hex_id=None)
		.execution_options(synchronize_session=False)
	)
	await session.execute(statement)
	await session.delete(campaign_map)
	await session.flush()
	return job

async def finish_map_deletion_cleanup(session: AsyncSession, map_id: UUID, master_id: UUID, *, root: Path) -> MapDeletionJob:
	"""Очистить файлы удалённой карты; фиксация отметки принадлежит вызывающему слою."""
	_require_uuid(map_id, "Карта")
	_require_uuid(master_id, "Мастер")
	job = await _get_map_deletion_job(session, map_id, master_id)

	if job is None:
		raise MapEntityNotFound("Задание очистки карты не найдено")

	await _require_deleted_map(session, map_id)

	if job.cleanup_complete:
		return job

	plan = deepcopy(job.cleanup_plan)
	cleanup.validate_map_cleanup_plan(plan, map_id, job.game_id, master_id, root=root)
	await _require_unshared_map_background(session, plan["background_storage_path"])

	task = asyncio.create_task(
		asyncio.to_thread(cleanup.execute_map_cleanup_plan, plan, map_id, job.game_id, master_id, root=root)
	)
	_, cancelled = await _wait_transfer_task(task)

	if cancelled:
		raise asyncio.CancelledError()

	job.cleanup_complete = True
	await session.flush()
	return job