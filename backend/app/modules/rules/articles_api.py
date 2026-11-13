# backend/app/modules/rules/articles_api.py

"""HTTP-маршруты самостоятельных статей правил."""

from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from backend.app.modules.rules.http import HttpCatalogQuery, RulesEditor, RulesRoute, RulesSession, RulesUser, rules_operation
from backend.app.modules.rules.schemas import articles as contracts
from backend.app.modules.rules.schemas.catalog import CatalogPage
from backend.app.modules.rules.services import article_service, catalog_service
from backend.app.web.csrf import enforce_csrf


router = APIRouter(prefix="/rules/articles", tags=["rules-articles"], route_class=RulesRoute)

CatalogFilters = Annotated[HttpCatalogQuery, Query()]
Create = contracts.RuleArticleCreate
Update = contracts.RuleArticleDraftUpdate
Publish = contracts.RuleArticlePublish
EditorRead = contracts.RuleArticleEditorRead
DraftRead = contracts.RuleArticleDraftRead
PublishRead = contracts.RuleArticlePublishRead
VersionRead = contracts.RuleArticleVersionRead

@router.get("", response_model=CatalogPage, operation_id="listRuleArticles")
async def list_articles(filters: CatalogFilters, session: RulesSession, user: RulesUser) -> CatalogPage:
	async with rules_operation(session):
		return await catalog_service.list_articles(session, user.id, filters)

@router.post("", response_model=EditorRead, status_code=201, dependencies=[Depends(enforce_csrf)], operation_id="createRuleArticle")
async def create_article(data: Create, session: RulesSession, user: RulesEditor) -> EditorRead:
	async with rules_operation(session, write=True):
		return await article_service.create_article(session, user.id, data)


@router.get("/{article_id}/draft", response_model=DraftRead, operation_id="getRuleArticleDraft")
async def get_draft(article_id: UUID, session: RulesSession, user: RulesEditor) -> DraftRead:
	async with rules_operation(session):
		return await article_service.get_article_draft(session, article_id, user.id)

@router.put("/{article_id}/draft", response_model=DraftRead, dependencies=[Depends(enforce_csrf)], operation_id="saveRuleArticleDraft")
async def save_draft(article_id: UUID, data: Update, session: RulesSession, user: RulesEditor) -> DraftRead:
	async with rules_operation(session, write=True):
		return await article_service.update_article_draft(session, article_id, user.id, data)

@router.post("/{article_id}/publish", response_model=PublishRead, dependencies=[Depends(enforce_csrf)], operation_id="publishRuleArticle")
async def publish(article_id: UUID, data: Publish, session: RulesSession, user: RulesEditor) -> PublishRead:
	async with rules_operation(session, write=True):
		return await article_service.publish_article(session, article_id, user.id, data)

@router.get("/{article_id}/versions/{version_id}", response_model=VersionRead, operation_id="getRuleArticleVersion")
async def get_version(article_id: UUID, version_id: UUID, session: RulesSession, user: RulesUser) -> VersionRead:
	async with rules_operation(session):
		return await article_service.get_article_version(session, article_id, version_id, user.id)