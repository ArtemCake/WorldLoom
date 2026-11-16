# backend/app/modules/rules/services/article_version_lookup.py

"""Поиск точной публикации с использованием существующих правил доступа."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.modules.rules import errors
from backend.app.modules.rules.models.articles import RuleArticleVersion
from backend.app.modules.rules.schemas.articles import RuleArticleVersionRead
from backend.app.modules.rules.services.article_service import get_article_version


_VERSIONS = RuleArticleVersion.__table__

async def get_version_by_id(session: AsyncSession, version_id: UUID, actor_id: UUID) -> RuleArticleVersionRead:
	"""Прочитать точную публикацию, не раскрывая содержание до проверки доступа."""
	if not isinstance(version_id, UUID) or not isinstance(actor_id, UUID):
		raise errors.InvalidRuleArticle("Некорректный идентификатор публикации или пользователя")

	if session.new or session.dirty or session.deleted:
		raise RuntimeError("Чтение публикации требует сессии без ожидающих ORM-изменений")

	if session.get_bind().dialect.name != "postgresql":
		raise RuntimeError("Сервис публикаций рассчитан на PostgreSQL")

	statement = select(_VERSIONS.c.article_id).where(_VERSIONS.c.id == version_id)
	article_id = (await session.execute(statement)).scalar_one_or_none()

	if article_id is None:
		raise errors.RuleArticleNotFound("Публикация статьи не найдена")

	return await get_article_version(session, article_id, version_id, actor_id)