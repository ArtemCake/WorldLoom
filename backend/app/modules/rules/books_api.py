# backend/app/modules/rules/books_api.py

"""HTTP-маршруты книг правил и чтения закреплённых статей."""

from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from backend.app.modules.rules.http import HttpCatalogQuery, RulesEditor, RulesRoute, RulesSession, RulesUser, rules_operation
from backend.app.modules.rules.schemas import books as contracts
from backend.app.modules.rules.schemas.catalog import BookReadingRead, CatalogPage
from backend.app.modules.rules.services import book_reader_service, book_service, catalog_service
from backend.app.web.csrf import enforce_csrf


router = APIRouter(prefix="/rules/books", tags=["rules-books"], route_class=RulesRoute)

CatalogFilters = Annotated[HttpCatalogQuery, Query()]
Create = contracts.RuleBookCreate
Update = contracts.RuleBookDraftUpdate
Publish = contracts.RuleBookPublish
EditorRead = contracts.RuleBookEditorRead
DraftRead = contracts.RuleBookDraftRead
PublishRead = contracts.RuleBookPublishRead
VersionRead = contracts.RuleBookVersionRead

@router.get("", response_model=CatalogPage, operation_id="listRuleBooks")
async def list_books(filters: CatalogFilters, session: RulesSession, user: RulesUser) -> CatalogPage:
	async with rules_operation(session):
		return await catalog_service.list_books(session, user.id, filters)

@router.post("", response_model=EditorRead, status_code=201, dependencies=[Depends(enforce_csrf)], operation_id="createRuleBook")
async def create_book(data: Create, session: RulesSession, user: RulesEditor) -> EditorRead:
	async with rules_operation(session, write=True):
		return await book_service.create_book(session, user.id, data)

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