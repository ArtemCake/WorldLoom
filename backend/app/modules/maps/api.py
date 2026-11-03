"""HTTP API карт без подключения к рабочему приложению."""

from __future__ import annotations
import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.bootstrap import AppResources
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.maps.errors import MapCommitOutcomeUnknown
from backend.app.modules.maps.schemas import FogOfWarRecalcIn, FogOfWarRecalcOut, HexGridGenerateIn, MapCreate, MapDeletionRead
from backend.app.modules.maps.schemas import MapGameTargetIn, MapGridSettings, MapLayerRead, MapPreviewIn, MapRead, MapUpdate, MapVisibilitySettings
from backend.app.modules.maps.services import map_image_service as images
from backend.app.modules.maps.services import map_management_service as management
from backend.app.modules.maps.services import map_preview_service as previews
from backend.app.modules.users.models.user import User
from backend.app.web.csrf import enforce_csrf
from backend.app.web.exception_handlers import MapErrorRoute
from backend.app.core.map_storage import get_map_images_root
from fastapi.responses import JSONResponse
from backend.app.modules.maps.services import map_hex_service as hexes



log = logging.getLogger(__name__)

router = APIRouter(prefix="/maps", tags=["maps"], route_class=MapErrorRoute)
WRITE_DEPENDENCIES = [Depends(enforce_csrf)]


def _get_resources(request: Request) -> AppResources:
	resources = getattr(request.app.state, "resources", None)

	if not isinstance(resources, AppResources):
		raise RuntimeError("Ресурсы приложения не подключены")

	return resources

async def _get_actor_id(user: User = Depends(get_current_user)) -> UUID:
	"""Не передавать ORM-пользователя в отдельную сессию операции."""
	return user.id

async def _get_operation_session(request: Request) -> AsyncIterator[AsyncSession]:
	"""Выдать сессию, отдельную от сессии проверки авторизации."""
	resources = _get_resources(request)

	async with resources.database.session() as session:
		yield session

def _get_image_root(request: Request) -> Path:
	"""Определить общий корень изображений для операций API карт."""
	return get_map_images_root(_get_resources(request).settings)

def _get_image_limits(request: Request) -> images.ImageLimits:
	settings = _get_resources(request).settings
	return images.ImageLimits(
		max_bytes=settings.MAP_IMAGE_MAX_BYTES,
		max_side=settings.MAP_IMAGE_MAX_SIDE,
		max_pixels=settings.MAP_IMAGE_MAX_PIXELS,
	)

def _validate_grid_settings(value: dict | None) -> None:
	"""Проверить пользовательские настройки до обращения к изменяющему сервису."""
	if value is None:
		return

	try:
		MapGridSettings.model_validate(value)

		if "visibility" in value:
			MapVisibilitySettings.model_validate(value["visibility"])
	except ValidationError:
		raise HTTPException(status_code=422, detail="Некорректные настройки сетки или видимости") from None

def _validate_update(data: MapUpdate) -> None:
	"""Не передавать явный null в обязательные поля сохранённой карты."""
	required_values = ("title", "grid_settings_json", "fog_of_war_enabled", "lighting_model")

	for name in required_values:
		if name in data.model_fields_set and getattr(data, name) is None:
			raise HTTPException(status_code=422, detail=f"Поле {name} не может быть null")

	_validate_grid_settings(data.grid_settings_json)

async def _commit_operation(session: AsyncSession) -> None:
	"""Зафиксировать внешнюю транзакцию, дождавшись результата при отмене."""
	task = asyncio.create_task(session.commit())
	cancelled = False

	while True:
		try:
			await asyncio.shield(task)
			break
		except asyncio.CancelledError:
			if task.cancelled():
				raise

			cancelled = True
		except Exception as error:
			log.error("Результат фиксации операции с картой не подтверждён. Тип ошибки: %s", type(error).__name__)
			raise MapCommitOutcomeUnknown("Результат сохранения операции не подтверждён") from error

	if cancelled:
		raise asyncio.CancelledError()


ActorId = Annotated[UUID, Depends(_get_actor_id)]
OperationSession = Annotated[AsyncSession, Depends(_get_operation_session)]
ImageRoot = Annotated[Path, Depends(_get_image_root)]
ImageLimits = Annotated[images.ImageLimits, Depends(_get_image_limits)]


@router.post("", response_model=MapRead, operation_id="createMap", dependencies=WRITE_DEPENDENCIES)
async def create_map(data: MapCreate, actor_id: ActorId, session: OperationSession, root: ImageRoot, limits: ImageLimits) -> MapRead:
	_validate_grid_settings(data.grid_settings_json)
	campaign_map = await management.create_map(session, actor_id, data, root=root, limits=limits)
	return MapRead.model_validate(campaign_map)

@router.post("/upload", response_model=MapRead, operation_id="createMapWithImage", dependencies=WRITE_DEPENDENCIES)
async def create_map_with_image(
		actor_id: ActorId, session: OperationSession, root: ImageRoot, limits: ImageLimits,
		game_id: UUID = Form(...), title: str = Form(..., min_length=1, max_length=255),
		fog_of_war_enabled: bool = Form(True), show_grid: bool = Form(True),
		rows: int = Form(20, ge=1, le=200), cols: int = Form(20, ge=1, le=200),
		background_image: UploadFile | None = File(None)) -> MapRead:
	data = MapCreate(
		game_id=game_id,
		title=title,
		map_type="image_upload",
		grid_settings_json={"rows": rows, "cols": cols, "show_grid": show_grid},
		fog_of_war_enabled=fog_of_war_enabled,
		lighting_model="basic",
	)
	campaign_map = await management.create_map(
		session, actor_id, data, root=root, limits=limits, background_image=background_image,
	)
	return MapRead.model_validate(campaign_map)

@router.post("/preview", operation_id="previewMapVisibility", dependencies=WRITE_DEPENDENCIES)
async def preview_map_visibility(payload: MapPreviewIn, actor_id: ActorId, session: OperationSession) -> dict:
	return await previews.preview(session, actor_id, payload)

@router.get("/by-game/{game_id}", response_model=list[MapRead], operation_id="listMapsForGame")
async def list_maps_for_game(game_id: UUID, actor_id: ActorId, session: OperationSession) -> list[MapRead]:
	campaign_maps = await management.list_maps_for_game(session, game_id, actor_id)
	return [MapRead.model_validate(campaign_map) for campaign_map in campaign_maps]

@router.get("/{map_id}/background", response_class=Response, operation_id="getMapBackground")
async def get_map_background(map_id: UUID, actor_id: ActorId, session: OperationSession, root: ImageRoot) -> Response:
	contents = await management.read_map_background(session, map_id, actor_id, root=root)
	return Response(
		content=contents,
		media_type="image/png",
		headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
	)

@router.get("/{map_id}", response_model=MapRead, operation_id="getMap")
async def get_map(map_id: UUID, actor_id: ActorId, session: OperationSession) -> MapRead:
	campaign_map = await management.get_map(session, map_id, actor_id)
	return MapRead.model_validate(campaign_map)

@router.patch("/{map_id}/upload", response_model=MapRead, operation_id="updateMapWithImage", dependencies=WRITE_DEPENDENCIES)
async def update_map_with_image(map_id: UUID, actor_id: ActorId, session: OperationSession, root: ImageRoot, limits: ImageLimits,
		title: str = Form(..., min_length=1, max_length=255), fog_of_war_enabled: bool = Form(...),
		background_image: UploadFile | None = File(None)) -> MapRead:
	data = MapUpdate(title=title, fog_of_war_enabled=fog_of_war_enabled)
	campaign_map = await management.update_map(
		session, map_id, actor_id, data, root=root, limits=limits, background_image=background_image,
	)
	return MapRead.model_validate(campaign_map)

@router.patch("/{map_id}", response_model=MapRead, operation_id="updateMap", dependencies=WRITE_DEPENDENCIES)
async def update_map(map_id: UUID, data: MapUpdate, actor_id: ActorId, session: OperationSession, root: ImageRoot, limits: ImageLimits) -> MapRead:
	_validate_update(data)
	campaign_map = await management.update_map(session, map_id, actor_id, data, root=root, limits=limits)
	return MapRead.model_validate(campaign_map)

@router.post("/{map_id}/activate", response_model=MapRead, operation_id="activateMap", dependencies=WRITE_DEPENDENCIES)
async def activate_map(map_id: UUID, actor_id: ActorId, session: OperationSession) -> MapRead:
	campaign_map = await management.set_map_activity(session, map_id, actor_id, active=True)
	await _commit_operation(session)
	await session.refresh(campaign_map)
	return MapRead.model_validate(campaign_map)

@router.post("/{map_id}/deactivate", response_model=MapRead, operation_id="deactivateMap", dependencies=WRITE_DEPENDENCIES)
async def deactivate_map(map_id: UUID, actor_id: ActorId, session: OperationSession) -> MapRead:
	campaign_map = await management.set_map_activity(session, map_id, actor_id, active=False)
	await _commit_operation(session)
	await session.refresh(campaign_map)
	return MapRead.model_validate(campaign_map)

@router.post("/{map_id}/copy", response_model=MapRead, status_code=201, operation_id="copyMap", dependencies=WRITE_DEPENDENCIES)
async def copy_map(map_id: UUID, payload: MapGameTargetIn, actor_id: ActorId, session: OperationSession, root: ImageRoot) -> MapRead:
	campaign_map = await management.copy_map(
		session, map_id, actor_id, payload.source_game_id, payload.target_game_id, root=root,
	)
	return MapRead.model_validate(campaign_map)

@router.post("/{map_id}/move", response_model=MapRead, operation_id="moveMap", dependencies=WRITE_DEPENDENCIES)
async def move_map(map_id: UUID, payload: MapGameTargetIn, actor_id: ActorId, session: OperationSession, root: ImageRoot) -> MapRead:
	campaign_map = await management.move_map(
		session, map_id, actor_id, payload.source_game_id, payload.target_game_id, root=root,
	)
	return MapRead.model_validate(campaign_map)

@router.delete("/{map_id}", response_model=MapDeletionRead, operation_id="deleteMap", dependencies=WRITE_DEPENDENCIES)
async def delete_map(map_id: UUID, actor_id: ActorId, session: OperationSession, root: ImageRoot) -> MapDeletionRead:
	job = await management.stage_map_deletion(session, map_id, actor_id, root=root)
	cleanup_complete = job.cleanup_complete
	await _commit_operation(session)
	return MapDeletionRead(map_id=map_id, deleted=True, cleanup_complete=cleanup_complete)

@router.post("/{map_id}/cleanup", response_model=MapDeletionRead, operation_id="finishMapDeletionCleanup", dependencies=WRITE_DEPENDENCIES)
async def finish_map_deletion_cleanup(map_id: UUID, actor_id: ActorId, session: OperationSession, root: ImageRoot) -> MapDeletionRead:
	await management.finish_map_deletion_cleanup(session, map_id, actor_id, root=root)
	await _commit_operation(session)
	return MapDeletionRead(map_id=map_id, deleted=True, cleanup_complete=True)

@router.post("/{map_id}/hex-grid", response_model=MapLayerRead, operation_id="generateHexGrid", dependencies=WRITE_DEPENDENCIES)
async def generate_hex_grid(map_id: UUID, payload: HexGridGenerateIn, actor_id: ActorId, session: OperationSession) -> MapLayerRead:
	layer = await management.generate_hex_grid(session, map_id, actor_id, payload.rows, payload.cols)
	return MapLayerRead.model_validate(layer)

@router.post("/{map_id}/fog-of-war/recalc", response_model=FogOfWarRecalcOut, operation_id="recalcFogOfWar", dependencies=WRITE_DEPENDENCIES)
async def recalc_fog_of_war(map_id: UUID, payload: FogOfWarRecalcIn, actor_id: ActorId, session: OperationSession) -> FogOfWarRecalcOut:
	visible_ids = await management.recalc_fog_of_war(session, map_id, actor_id, payload.viewer_token_ids)
	return FogOfWarRecalcOut(visible_hex_ids=sorted(visible_ids))

@router.get("/{map_id}/hex-grid", response_class=JSONResponse, operation_id="getMapHexGrid")
async def get_map_hex_grid(map_id: UUID, actor_id: ActorId, session: OperationSession) -> JSONResponse:
	"""Прочитать идентификаторы и координаты гексов после проверки прав мастера."""
	await management.get_map(session, map_id, actor_id)
	state = await hexes.load_hex_grid(session, map_id)

	cells = [
		{
			"id": str(cell.id),
			"col": cell.axial_q + (cell.axial_r - (cell.axial_r & 1)) // 2,
			"row": cell.axial_r,
			"is_visible_to_players": cell.is_visible_to_players,
			"explored_by_players": cell.explored_by_players,
		}
		for cell in state.hexes
	]

	return JSONResponse(
		content={"map_id": str(map_id), "cells": cells},
		headers={"Cache-Control": "private, no-store"},
	)