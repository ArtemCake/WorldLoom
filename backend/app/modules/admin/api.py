# backend/app/modules/admin/api.py

"""Административный API правил систем и переиспользуемых основ.

Другие административные разделы переносятся отдельно.
Транзакциями управляет HTTP-адаптер, а не предметные сервисы.
"""

from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.game_systems.errors import GameSystemError, GameSystemDeletionBlocked, GameSystemNotFound, GameSystemRulesConflict, GameSystemRulesStorageError, InvalidGameSystemRules
from backend.app.modules.game_systems.schemas.game_rules import (GameSystemRulesDraftCreate, GameSystemRulesDraftRead, GameSystemRulesDraftState, GameSystemRulesDraftUpdate,
	GameSystemRulesPublish, GameSystemRulesPublishedState, GameSystemRulesVersionRead)
from backend.app.modules.game_systems.schemas.game_system_origin import (GameSystemDraftEngineSet, GameSystemEngineEditorUpdate,
    GameSystemEngineOriginRead, GameSystemFromEngineCreate)
from backend.app.modules.game_systems.schemas.rules.rule_engine_lifecycle import RuleEngineRemovalPreview
from backend.app.modules.game_systems.schemas.rules.rule_engine_removal import RuleEngineRemovalPlan
from backend.app.modules.game_systems.schemas.rules.rule_engines import (RuleEngineActivityUpdate, RuleEngineCreate, RuleEngineDelete, RuleEngineDeleteRead, RuleEngineDraftRead,
                                                                         RuleEngineDraftUpdate, RuleEngineEditorRead, RuleEnginePage, RuleEnginePublish, RuleEngineRead, RuleEngineVersionPage, RuleEngineVersionRead)
from backend.app.modules.game_systems.services import editor_service
from backend.app.modules.game_systems.services import rule_engine_lifecycle_service as lifecycle
from backend.app.modules.game_systems.services import rule_engine_removal_service as removal
from backend.app.modules.game_systems.services import rule_engine_service as engines
from backend.app.modules.users.models.user import User
from backend.app.web.csrf import enforce_csrf
from backend.app.modules.game_systems.schemas.game_system_editor import GameSystemEditorCreate, GameSystemEditorRead, GameSystemEditorUpdate
from backend.app.modules.game_systems.services.delete_service import delete_game_system
from backend.app.modules.game_systems.schemas.game_rules import GameSystemRulesVersionPage


logger = logging.getLogger(__name__)

SessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
ContentManagerDependency = Annotated[User, Depends(require_content_manager)]

def _content_actor_id(actor: ContentManagerDependency) -> UUID:
	"""Получить идентификатор только из проверенного пользователя."""
	actor_id = getattr(actor, "id", None)

	if not isinstance(actor_id, UUID):
		raise HTTPException(
			status_code=401,
			detail="Требуется авторизованный пользователь",
			headers={"Cache-Control": "no-store"},
		)

	return actor_id

ActorDependency = Annotated[UUID, Depends(_content_actor_id)]

router = APIRouter(
	prefix="/admin",
	tags=["admin"],
	dependencies=[Depends(require_content_manager)],
	responses={
		401: {"description": "Авторизация не подтверждена"},
		403: {"description": "Недостаточно прав"},
		404: {"description": "Система, основа или публикация не найдена"},
		409: {"description": "Конфликт состояния или ограничений данных"},
		422: {"description": "Некорректные входные данные"},
		500: {"description": "Внутренняя ошибка"},
	},
)

def _http_error(status_code: int, detail: str) -> HTTPException:
	return HTTPException(status_code=status_code, detail=detail, headers={"Cache-Control": "no-store"})

def _rules_http_error(error: GameSystemError) -> HTTPException:
	"""Не возвращать клиенту текст внутренних исключений."""
	if isinstance(error, GameSystemNotFound):
		return _http_error(404, "Игровая система, основа или публикация не найдена")

	if isinstance(error, GameSystemDeletionBlocked):
		return _http_error(
			409,
			"Удаление блокируют связанные данные: "
			+ ", ".join(error.blockers)
			+ ". Сначала удалите их или деактивируйте систему",
			)
	if isinstance(error, GameSystemRulesConflict):
		return _http_error(
			409,
			"Операция несовместима с текущим состоянием данных. "
			"Получите актуальное состояние и проверьте ревизию, "
			"происхождение правил, активность и наличие публикаций",
		)

	if isinstance(error, InvalidGameSystemRules):
		return _http_error(422, "Входные данные или профиль правил не прошли проверку")

	if isinstance(error, GameSystemRulesStorageError):
		return _http_error(500, "Не удалось прочитать сохранённые правила")

	return _http_error(500, "Не удалось выполнить операцию с правилами")

def _integrity_http_error(error: IntegrityError) -> HTTPException:
	"""Преобразовать известные нарушения PostgreSQL без разбора текста SQL."""
	original = error.orig
	cause = getattr(original, "__cause__", None)
	sqlstate = (
			getattr(original, "sqlstate", None)
			or getattr(original, "pgcode", None)
			or getattr(cause, "sqlstate", None)
			or getattr(cause, "pgcode", None)
	)

	if sqlstate == "23505":
		return _http_error(
			409,
			"Операция нарушает уникальность данных. "
			"Проверьте идентификатор основы и актуальное состояние публикаций",
		)

	if sqlstate == "23503":
		return _http_error(
			409,
			"Операция конфликтует со связанными данными. "
			"Обновите состояние; удаление используемых данных может быть запрещено",
		)

	return _http_error(500, "Не удалось сохранить данные правил")

@asynccontextmanager
async def _rules_operation(session: AsyncSession, *, write: bool) -> AsyncIterator[None]:
	"""Завершить транзакцию до успешного возврата результата."""
	try:
		yield

		if write:
			await session.commit()
		else:
			await session.rollback()

	except GameSystemError as exc:
		await session.rollback()
		error = _rules_http_error(exc)

		if error.status_code >= 500:
			logger.exception("Ошибка административной операции правил")

		raise error from exc

	except IntegrityError as exc:
		await session.rollback()
		error = _integrity_http_error(exc)

		if error.status_code >= 500:
			logger.exception("Неизвестное нарушение ограничений при операции правил")

		raise error from exc

	except BaseException:
		await session.rollback()
		raise

@router.get("/game-systems/{system_id}/rules/draft", response_model=GameSystemRulesDraftState, operation_id="adminGetGameSystemRulesDraft")
async def get_rules_draft(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemRulesDraftState:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await editor_service.get_rules_draft(session, system_id)

@router.post("/game-systems/{system_id}/rules/draft", response_model=GameSystemRulesDraftRead, status_code=201, operation_id="adminCreateGameSystemRulesDraft",
	dependencies=[Depends(enforce_csrf)])
async def create_rules_draft(system_id: UUID, data: GameSystemRulesDraftCreate, response: Response, session: SessionDependency) -> GameSystemRulesDraftRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.create_rules_draft(session, system_id, data)

@router.patch("/game-systems/{system_id}/rules/draft", response_model=GameSystemRulesDraftRead, operation_id="adminUpdateGameSystemRulesDraft",
	dependencies=[Depends(enforce_csrf)])
async def update_rules_draft(system_id: UUID, data: GameSystemRulesDraftUpdate, response: Response, session: SessionDependency) -> GameSystemRulesDraftRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.update_rules_draft(session, system_id, data)

@router.put("/game-systems/{system_id}/rules/engine", response_model=GameSystemRulesDraftRead, operation_id="adminSetGameSystemRulesEngine",
            dependencies=[Depends(enforce_csrf)])
async def set_rules_engine(system_id: UUID, data: GameSystemDraftEngineSet, response: Response, session: SessionDependency, actor: ContentManagerDependency) -> GameSystemRulesDraftRead:
	response.headers["Cache-Control"] = "no-store"
	actor_id = _content_actor_id(actor)

	async with _rules_operation(session, write=True):
		return await editor_service.set_rules_draft_engine(session, system_id, actor_id, data)

@router.post("/game-systems/{system_id}/rules/publish", response_model=GameSystemRulesVersionRead, status_code=201, operation_id="adminPublishGameSystemRules",
	dependencies=[Depends(enforce_csrf)])
async def publish_rules(system_id: UUID, data: GameSystemRulesPublish, response: Response, session: SessionDependency) -> GameSystemRulesVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.publish_rules_version(session, system_id, data)

@router.get("/game-systems/{system_id}/rules/latest", response_model=GameSystemRulesPublishedState, operation_id="adminGetGameSystemPublishedRules")
async def get_latest_rules(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemRulesPublishedState:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		version = await editor_service.get_latest_rules_version(session, system_id, active_only=False)
		return GameSystemRulesPublishedState(version=version)

@router.get("/game-systems/{system_id}/rules/versions", response_model=GameSystemRulesVersionPage)
async def get_rules_history(system_id: UUID, response: Response, session: SessionDependency, limit: int = 20, before: int | None = None):
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await editor_service.list_publications(session, system_id, active_only=False, limit=limit, before=before)

@router.get("/game-systems/{system_id}/rules/versions/{version_id}", response_model=GameSystemRulesVersionRead)
async def get_system_rules_version(system_id: UUID, version_id: UUID, response: Response, session: SessionDependency):
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await editor_service.get_rules_version(session, system_id, version_id, active_only=False)


@router.get("/rule-engines", response_model=RuleEnginePage, operation_id="adminListRuleEngines")
async def list_engines(response: Response, session: SessionDependency, actor_id: ActorDependency, owned_only: bool = False, limit: int = Query(default=50, ge=1, le=100),
		offset: int = Query(default=0, ge=0)) -> RuleEnginePage:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await engines.list_rule_engines(session, actor_id, owned_only=owned_only, limit=limit, offset=offset)

@router.post("/rule-engines", response_model=RuleEngineEditorRead, status_code=201, operation_id="adminCreateRuleEngine", dependencies=[Depends(enforce_csrf)])
async def create_engine(data: RuleEngineCreate, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineEditorRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await engines.create_engine_with_draft(session, actor_id, data)

@router.get("/rule-engines/{engine_id}/draft", response_model=RuleEngineDraftRead, operation_id="adminGetRuleEngineDraft")
async def get_engine_draft(engine_id: UUID, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineDraftRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await engines.get_engine_draft(session, engine_id, actor_id)

@router.put("/rule-engines/{engine_id}/draft", response_model=RuleEngineDraftRead, operation_id="adminSaveRuleEngineDraft", dependencies=[Depends(enforce_csrf)])
async def save_engine_draft(engine_id: UUID, data: RuleEngineDraftUpdate, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineDraftRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await engines.update_engine_draft(session, engine_id, actor_id, data)

@router.post("/rule-engines/{engine_id}/publish", response_model=RuleEngineVersionRead, status_code=201, operation_id="adminPublishRuleEngine",
	dependencies=[Depends(enforce_csrf)])
async def publish_engine(engine_id: UUID, data: RuleEnginePublish, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await engines.publish_engine_version(session, engine_id, actor_id, data)

@router.get("/rule-engines/{engine_id}/versions", response_model=RuleEngineVersionPage, operation_id="adminListRuleEngineVersions")
async def list_versions(engine_id: UUID, response: Response, session: SessionDependency, actor_id: ActorDependency, limit: int = Query(default=50, ge=1, le=100),
		offset: int = Query(default=0, ge=0)) -> RuleEngineVersionPage:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await engines.list_engine_versions(session, engine_id, actor_id, limit=limit, offset=offset)

@router.get("/rule-engines/{engine_id}/versions/{version_id}", response_model=RuleEngineVersionRead, operation_id="adminGetRuleEngineVersion")
async def get_version(engine_id: UUID, version_id: UUID, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await engines.get_engine_version(session, engine_id, version_id, actor_id)

@router.patch("/rule-engines/{engine_id}/activity", response_model=RuleEngineRead, operation_id="adminSetRuleEngineActivity", dependencies=[Depends(enforce_csrf)])
async def set_engine_activity(engine_id: UUID, data: RuleEngineActivityUpdate, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await engines.set_engine_activity(session, engine_id, actor_id, data)

@router.delete("/rule-engines/{engine_id}", response_model=RuleEngineDeleteRead, operation_id="adminDeleteUnpublishedRuleEngine", dependencies=[Depends(enforce_csrf)])
async def delete_engine(engine_id: UUID, data: RuleEngineDelete, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineDeleteRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await engines.delete_unpublished_engine(session, engine_id, actor_id, data)

@router.get("/rule-engines/{engine_id}/removal-preview", response_model=RuleEngineRemovalPreview, operation_id="adminPreviewRuleEngineRemoval")
async def preview_engine_removal(engine_id: UUID, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineRemovalPreview:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await lifecycle.preview_engine_removal(session, engine_id, actor_id)

@router.get("/rule-engines/{engine_id}/removal-plan", response_model=RuleEngineRemovalPlan, operation_id="adminGetRuleEngineRemovalPlan")
async def get_engine_removal_plan(engine_id: UUID, response: Response, session: SessionDependency, actor_id: ActorDependency) -> RuleEngineRemovalPlan:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await removal.get_removal_plan(session, engine_id, actor_id)

@router.post("/game-systems/editor/create", response_model=GameSystemEditorRead, status_code=201,
             operation_id="adminCreateGameSystemWithDraft", dependencies=[Depends(enforce_csrf)])
async def create_system_with_draft(data: GameSystemEditorCreate, response: Response, session: SessionDependency) -> GameSystemEditorRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.create_system_with_draft(session, data)

@router.put("/game-systems/{system_id}/editor", response_model=GameSystemEditorRead, operation_id="adminSaveGameSystemWithDraft",
            dependencies=[Depends(enforce_csrf)])
async def save_system_with_draft(system_id: UUID, data: GameSystemEditorUpdate, response: Response, session: SessionDependency) -> GameSystemEditorRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.update_system_with_draft(session, system_id, data)

@router.post("/game-systems/from-engine", response_model=GameSystemEditorRead, status_code=201,
             operation_id="adminCreateGameSystemFromEngine", dependencies=[Depends(enforce_csrf)])
async def create_system_from_engine(data: GameSystemFromEngineCreate, response: Response, session: SessionDependency,
                                    actor_id: ActorDependency) -> GameSystemEditorRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.create_system_from_engine(session, actor_id, data)

@router.get("/game-systems/{system_id}/editor/engine", response_model=GameSystemEngineOriginRead, operation_id="adminGetGameSystemEngineOrigin")
async def get_system_engine_origin(system_id: UUID, response: Response, session: SessionDependency) -> GameSystemEngineOriginRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=False):
		return await editor_service.get_system_engine_origin(session, system_id)

@router.put("/game-systems/{system_id}/editor/engine", response_model=GameSystemEditorRead,
            operation_id="adminUpdateGameSystemFromEngine", dependencies=[Depends(enforce_csrf)])
async def save_system_from_engine(system_id: UUID, data: GameSystemEngineEditorUpdate, response: Response, session: SessionDependency,
                                  actor_id: ActorDependency) -> GameSystemEditorRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.update_system_from_engine(session, system_id, actor_id, data)

@router.delete("/game-systems/{system_id}", operation_id="adminDeleteGameSystem", dependencies=[Depends(enforce_csrf)])
async def remove_game_system(system_id: UUID, response: Response, session: SessionDependency) -> dict:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await delete_game_system(session, system_id)

@router.post("/game-systems/{system_id}/rules/current/{version_id}", response_model=GameSystemRulesVersionRead, operation_id="adminSetCurrentGameSystemRulesVersion",
	dependencies=[Depends(enforce_csrf)])
async def set_current_rules_version(system_id: UUID, version_id: UUID, response: Response, session: SessionDependency) -> GameSystemRulesVersionRead:
	response.headers["Cache-Control"] = "no-store"

	async with _rules_operation(session, write=True):
		return await editor_service.set_current_rules_version(session, system_id, version_id)