# tests/python/rules/test_rules_pages.py

"""Проверки подключения HTML-каталога и его шаблона."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from fastapi_csrf_protect import CsrfProtect
from httpx import ASGITransport, AsyncClient
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, select_autoescape
from starlette.responses import HTMLResponse
from backend.app.infrastructure.database.session import get_async_session
from backend.app.modules.rules.services import system_catalog
from backend.app.modules.auth.dependencies import get_optional_user
from backend.app.modules.rules.pages import router


class RulesPageTests(unittest.IsolatedAsyncioTestCase):

	async def test_authorized_page_passes_system_options_to_renderer(self):
		self.actor = SimpleNamespace(id="test-user")
		options = [{"id": "test-system", "name": "Тестовая система"}]
		self.system_options.return_value = options

		def render(*args):
			self.session.rollback.assert_not_awaited()
			return HTMLResponse("<main>Правила</main>")

		renderer = Mock(side_effect=render)

		with patch("backend.app.modules.rules.pages.render_page", renderer):
			response = await self.client.get("/rules/catalog")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(renderer.call_args.args[2]["rule_systems"], options)
		self.system_options.assert_awaited_once_with(self.session)
		self.session.rollback.assert_awaited_once()
		self.session.commit.assert_not_awaited()

	async def test_system_options_failure_releases_read_transaction(self):
		self.actor = SimpleNamespace(id="test-user")
		self.system_options.side_effect = RuntimeError("Ошибка чтения")

		with self.assertRaisesRegex(RuntimeError, "Ошибка чтения"):
			await self.client.get("/rules/catalog")

		self.session.rollback.assert_awaited_once()
		self.session.commit.assert_not_awaited()

	async def asyncSetUp(self):
		self.app = FastAPI()
		self.app.include_router(router)
		self.actor = None
		self.csrf = object()

		self.session = SimpleNamespace(
			new=set(),
			dirty=set(),
			deleted=set(),
			in_transaction=Mock(return_value=True),
			in_nested_transaction=Mock(return_value=False),
			begin=AsyncMock(),
			commit=AsyncMock(),
			rollback=AsyncMock(),
		)
		self.system_options = AsyncMock(return_value=[])
		service_patch = patch.object(system_catalog, "list_active_system_options", self.system_options)
		service_patch.start()
		self.addCleanup(service_patch.stop)

		async def session_dependency():
			return self.session

		self.app.dependency_overrides[get_async_session] = session_dependency

		async def optional_user():
			return self.actor

		async def csrf_dependency():
			return self.csrf

		self.app.dependency_overrides[get_optional_user] = optional_user
		self.app.dependency_overrides[CsrfProtect] = csrf_dependency
		self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")

	async def asyncTearDown(self):
		await self.client.aclose()

	async def test_catalog_uses_shared_renderer_and_disables_cache(self):
		renderer = Mock(side_effect=lambda *args: HTMLResponse("<main>Правила</main>"))

		with patch("backend.app.modules.rules.pages.render_page", renderer):
			response = await self.client.get("/rules/catalog")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.headers["cache-control"], "no-store")
		args = renderer.call_args.args
		self.assertEqual(args[1], "rules/catalog.html")
		self.assertEqual(args[2], {"user": None, "rule_systems": []})
		self.system_options.assert_not_awaited()
		self.session.rollback.assert_not_awaited()
		self.assertIs(args[3], self.csrf)

	async def test_authorized_user_is_passed_to_template(self):
		self.actor = SimpleNamespace(id="test-user")
		renderer = Mock(side_effect=lambda *args: HTMLResponse("<main>Правила</main>"))

		with patch("backend.app.modules.rules.pages.render_page", renderer):
			response = await self.client.get("/rules/catalog")

		self.assertEqual(response.status_code, 200)
		self.assertIs(renderer.call_args.args[2]["user"], self.actor)

	def test_page_router_does_not_register_json_api(self):
		paths = {route.path for route in router.routes}
		self.assertEqual(paths, {"/rules/catalog"})

class RulesTemplateTests(unittest.TestCase):

	def test_system_selector_keeps_general_catalog_option(self):
		systems = [{"id": "system-one", "name": "Первая система"}]
		html = self.template.render(user=object(), project_name="WorldLoom", rule_systems=systems)

		self.assertIn('name="system_id"', html)
		self.assertIn("data-rules-system", html)
		self.assertIn('<option value="">Все системы</option>', html)
		self.assertIn('<option value="system-one">Первая система</option>', html)

	def test_system_names_are_escaped(self):
		systems = [{"id": "system-one", "name": "<script>unsafe()</script>"}]
		html = self.template.render(user=object(), project_name="WorldLoom", rule_systems=systems)

		self.assertNotIn("<script>unsafe()</script>", html)
		self.assertIn("&lt;script&gt;unsafe()&lt;/script&gt;", html)

	@classmethod
	def setUpClass(cls):
		root = Path(__file__).resolve().parents[3]
		base = DictLoader({"base.html": "{% block content %}{% endblock %}"})
		files = FileSystemLoader(str(root / "frontend" / "templates"))
		environment = Environment(loader=ChoiceLoader([base, files]), autoescape=select_autoescape(["html"]))
		cls.template = environment.get_template("rules/catalog.html")

	def test_guest_sees_login_without_catalog_loader(self):
		html = self.template.render(user=None, project_name="WorldLoom")
		self.assertIn('href="/login"', html)
		self.assertNotIn("data-rules-catalog", html)

	def test_user_sees_filters_and_catalog_controls(self):
		html = self.template.render(user=object(), project_name="WorldLoom")

		for marker in ("data-rules-catalog", "data-rules-filters", "data-rules-list", "data-rules-more"):
			self.assertIn(marker, html)

		self.assertNotIn('name="kind"', html)
		self.assertNotIn('value="articles"', html)
		self.assertIn("data-rules-catalog-panel", html)
		self.assertIn("data-rules-reader", html)
		self.assertIn("data-rules-reader-back", html)
		self.assertIn("К списку книг", html)


if __name__ == "__main__":
	unittest.main()
