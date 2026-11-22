# tests/python/rules/test_admin_workspace_route.py

"""HTTP-граница обзора рабочего пространства системы (§5.1, этап C).

Проверяет без PostgreSQL: маршрут подключён, авторизация обязательна,
чтение не выполняет commit и передаёт системный идентификатор сервиса.
"""

from __future__ import annotations
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.admin.api import router
from backend.app.modules.admin.dependencies import require_content_manager
from backend.app.modules.auth.dependencies import get_current_user
from backend.app.modules.game_systems.errors import GameSystemNotFound
from backend.app.modules.rules.schemas.workspace_overview import (WorkspaceOverview, WorkspaceRulesOverview, WorkspaceSystemPassport)
from backend.app.modules.rules.services import workspace_overview
from backend.app.web.csrf import enforce_csrf


class FakeSession:
	def __init__(self):
		self.new = set()
		self.dirty = set()
		self.deleted = set()
		self.active = True
		self.nested = False
		self.begin = AsyncMock(side_effect=self._begin)
		self.commit = AsyncMock(side_effect=self._finish)
		self.rollback = AsyncMock(side_effect=self._finish)

	def in_transaction(self):
		return self.active

	def in_nested_transaction(self):
		return self.nested

	async def _begin(self):
		self.active = True

	async def _finish(self):
		self.active = False


def make_overview(system_id):
	now = __import__("datetime").datetime(2026, 11, 19, tzinfo=__import__("datetime").timezone.utc)

	return WorkspaceOverview(
		system=WorkspaceSystemPassport(
			id=system_id,
			name="Прокси",
			slug="proxy",
			description=None,
			is_active=False,
			rules_engine_version="1.0",
			created_at=now,
			updated_at=now,
		),
		rules=WorkspaceRulesOverview(),
	)


class AdminWorkspaceRouteTests(unittest.IsolatedAsyncioTestCase):

	async def asyncSetUp(self):
		self.session = FakeSession()
		self.actor = SimpleNamespace(id=uuid4(), roles=[], admin_permissions=[])
		self.app = FastAPI()
		self.app.include_router(router)

		async def session_dependency():
			yield self.session

		async def user_dependency():
			return self.actor

		async def csrf_dependency():
			return None

		self.app.dependency_overrides[get_async_session] = session_dependency
		self.app.dependency_overrides[get_current_user] = user_dependency
		self.app.dependency_overrides[require_content_manager] = user_dependency
		self.app.dependency_overrides[enforce_csrf] = csrf_dependency
		self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")

	async def asyncTearDown(self):
		await self.client.aclose()

	async def test_workspace_route_passes_path_system_id(self):
		system_id = uuid4()
		mock = AsyncMock(return_value=make_overview(system_id))

		with patch.object(workspace_overview, "get_workspace_overview", mock):
			response = await self.client.get(f"/admin/game-systems/{system_id}/workspace")

		self.assertEqual(response.status_code, 200, response.text)
		args = mock.await_args.args
		self.assertIs(args[0], self.session)
		self.assertEqual(args[1], system_id)
		self.assertEqual(response.json()["system"]["id"], str(system_id))
		self.assertEqual(response.headers["cache-control"], "no-store")
		self.session.commit.assert_not_awaited()
		self.session.rollback.assert_awaited_once()

	async def test_workspace_route_maps_missing_system_to_404(self):
		mock = AsyncMock(side_effect=GameSystemNotFound("Игровая система не найдена"))

		with patch.object(workspace_overview, "get_workspace_overview", mock):
			response = await self.client.get(f"/admin/game-systems/{uuid4()}/workspace")

		self.assertEqual(response.status_code, 404)
		self.session.commit.assert_not_awaited()

	async def test_workspace_route_requires_content_manager(self):
		del self.app.dependency_overrides[require_content_manager]
		mock = AsyncMock(return_value=make_overview(uuid4()))

		with patch.object(workspace_overview, "get_workspace_overview", mock):
			response = await self.client.get(f"/admin/game-systems/{uuid4()}/workspace")

		self.assertIn(response.status_code, (401, 403))
		mock.assert_not_awaited()


if __name__ == "__main__":
	unittest.main()
