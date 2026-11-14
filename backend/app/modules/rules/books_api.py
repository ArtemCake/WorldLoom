# backend/app/modules/rules/books_api.py

"""HTTP-маршруты книг правил и чтения закреплённых статей."""

from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from backend.app.modules.rules.http import HttpCatalogQuery, RulesEditor, RulesRoute, RulesSession, RulesUser, rules_operation
from backend.app.modules.rules.schemas.books import books as contracts
from backend.app.modules.rules.schemas.catalog import BookReadingRead, CatalogPage
from backend.app.modules.rules.services import catalog_service
from backend.app.modules.rules.services.books import book_service, book_working_publication, book_reader_service, book_authoring
from backend.app.web.csrf import enforce_csrf
from backend.app.modules.rules.http import HttpBookCatalogQuery
from backend.app.modules.rules.schemas import system_books as system_contracts
from backend.app.modules.rules.services import system_books as system_book_service
from backend.app.modules.rules.http import HttpAuthorBookQuery
from backend.app.modules.rules.schemas.books.book_authoring import AuthorBookPage
from backend.app.modules.rules.schemas.books.book_working_draft import BookWorkingDraftRead, BookWorkingDraftUpdate
from backend.app.modules.rules.schemas.books.book_working_draft import BookWorkingEditorRead
from backend.app.modules.rules.services.books import book_working_editor


router = APIRouter(prefix="/rules/books", tags=["rules-books"], route_class=RulesRoute)

CatalogFilters = Annotated[HttpBookCatalogQuery, Query()]
AuthorFilters = Annotated[HttpAuthorBookQuery, Query()]
Create = system_contracts.SystemBookCreate
Update = contracts.RuleBookDraftUpdate
Publish = contracts.RuleBookPublish
EditorRead = contracts.RuleBookEditorRead
DraftRead = contracts.RuleBookDraftRead
PublishRead = contracts.RuleBookPublishRead
VersionRead = contracts.RuleBookVersionRead
AssignSystem = system_contracts.BookSystemAssign
AssignmentRead = system_contracts.BookSystemAssignmentRead
WorkingRead = BookWorkingDraftRead
WorkingUpdate = BookWorkingDraftUpdate

ASSIGN_SYSTEM_OPTIONS = {
	"response_model": AssignmentRead,
	"dependencies": [Depends(enforce_csrf)],
	"operation_id": "assignRuleBookSystem",
}

WORKING_PUBLISH_OPTIONS = {
	"response_model": PublishRead,
	"dependencies": [Depends(enforce_csrf)],
	"operation_id": "publishRuleBookWorkingDraft",
}

@router.get("", response_model=CatalogPage, operation_id="listRuleBooks")
async def list_books(filters: CatalogFilters, session: RulesSession, user: RulesUser) -> CatalogPage:
	common = HttpCatalogQuery.model_validate(filters.model_dump(exclude={"system_id"}))
	async with rules_operation(session):
		return await catalog_service.list_books(session, user.id, common, system_id=filters.system_id)

@router.post("", response_model=EditorRead, status_code=201, dependencies=[Depends(enforce_csrf)], operation_id="createRuleBook")
async def create_book(data: Create, session: RulesSession, user: RulesEditor) -> EditorRead:
	async with rules_operation(session, write=True):
		return await system_book_service.create_system_book(session, user.id, data)

@router.get("/authoring", response_model=AuthorBookPage, operation_id="listAuthorRuleBooks")
async def list_author_books(filters: AuthorFilters, session: RulesSession, user: RulesEditor) -> AuthorBookPage:
	async with rules_operation(session):
		return await book_authoring.list_author_books(session, user.id, filters)

@router.put("/{book_id}/system", **ASSIGN_SYSTEM_OPTIONS)
async def assign_system(book_id: UUID, data: AssignSystem, session: RulesSession, user: RulesEditor) -> AssignmentRead:
	async with rules_operation(session, write=True):
		return await system_book_service.assign_book_system(session, book_id, user.id, data)

@router.get("/{book_id}/editor", response_model=EditorRead, operation_id="getRuleBookEditor")
async def get_editor(book_id: UUID, session: RulesSession, user: RulesEditor) -> EditorRead:
	async with rules_operation(session):
		return await book_service.get_book_editor(session, book_id, user.id)

@router.get("/{book_id}/draft", response_model=DraftRead, operation_id="getRuleBookDraft")
async def get_draft(book_id: UUID, session: RulesSession, user: RulesEditor) -> DraftRead:
	async with rules_operation(session):
		return await book_service.get_book_draft(session, book_id, user.id)

@router.put("/{book_id}/draft", response_model=DraftRead, dependencies=[Depends(enforce_csrf)], operation_id="saveRuleBookDraft")
async def save_draft(book_id: UUID, data: Update, session: RulesSession, user: RulesEditor) -> DraftRead:
	async with rules_operation(session, write=True):
		return await book_service.update_book_draft(session, book_id, user.id, data)

@router.post("/{book_id}/publish", response_model=PublishRead, dependencies=[Depends(enforce_csrf)], operation_id="publishRuleBook")
async def publish(book_id: UUID, data: Publish, session: RulesSession, user: RulesEditor) -> PublishRead:
	async with rules_operation(session, write=True):
		return await book_service.publish_book(session, book_id, user.id, data)

@router.get("/{book_id}/versions/{version_id}", response_model=VersionRead, operation_id="getRuleBookVersion")
async def get_version(book_id: UUID, version_id: UUID, session: RulesSession, user: RulesUser) -> VersionRead:
	async with rules_operation(session):
		return await book_service.get_book_version(session, book_id, version_id, user.id)

@router.get("/{book_id}/versions/{version_id}/reading", response_model=BookReadingRead, operation_id="readRuleBook")
async def read_book(book_id: UUID, version_id: UUID, session: RulesSession, user: RulesUser) -> BookReadingRead:
	async with rules_operation(session):
		return await book_reader_service.read_book(session, book_id, version_id, user.id)

@router.get("/{book_id}/working-draft", response_model=WorkingRead, operation_id="getRuleBookWorkingDraft")
async def get_working_draft(book_id: UUID, session: RulesSession, user: RulesEditor) -> WorkingRead:
	async with rules_operation(session):
		return await book_service.get_working_draft(session, book_id, user.id)

@router.put("/{book_id}/working-draft", response_model=WorkingRead, dependencies=[Depends(enforce_csrf)], operation_id="saveRuleBookWorkingDraft")
async def save_working_draft(book_id: UUID, data: WorkingUpdate, session: RulesSession, user: RulesEditor) -> WorkingRead:
	async with rules_operation(session, write=True):
		return await book_service.update_working_draft(session, book_id, user.id, data)

@router.post("/{book_id}/working-draft/publish", **WORKING_PUBLISH_OPTIONS)
async def publish_working_draft(book_id: UUID, data: Publish, session: RulesSession, user: RulesEditor) -> PublishRead:
	async with rules_operation(session, write=True):
		return await book_working_publication.publish_working_book(session, book_id, user.id, data)

@router.get("/{book_id}/working-editor", response_model=BookWorkingEditorRead, operation_id="getRuleBookWorkingEditor")
async def get_working_editor(book_id: UUID, session: RulesSession, user: RulesEditor) -> BookWorkingEditorRead:
	async with rules_operation(session):
		return await book_working_editor.get_working_editor(session, book_id, user.id)