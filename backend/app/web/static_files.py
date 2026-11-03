# backend/app/web/static_files.py

"""Выдача собранного frontend без исходников и закрытых каталогов."""

from os import stat_result
from pathlib import Path, PurePosixPath
from fastapi import FastAPI
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope
from backend.app.core.paths import FRONTEND_DIST_DIR
from backend.app.web.assets import STATIC_URL_PREFIX


def _blocked_parts(parts: tuple[str, ...]) -> bool:
	return any(part.startswith(".") or part == "private" for part in parts)

class PublicStaticFiles(StaticFiles):
	"""Сохранить запрет private и закрыть скрытые файлы, включая manifest."""

	def lookup_path(self, path: str) -> tuple[str, stat_result | None]:
		parts = PurePosixPath(path.replace("\\", "/")).parts

		if _blocked_parts(parts):
			return "", None

		full_path, info = super().lookup_path(path)

		if not full_path or info is None:
			return full_path, info

		root = Path(self.directory).resolve()

		try:
			relative = Path(full_path).resolve().relative_to(root)
		except ValueError:
			return "", None

		if _blocked_parts(relative.parts):
			return "", None

		return full_path, info

	async def get_response(self, path: str, scope: Scope) -> Response:
		response = await super().get_response(path, scope)
		response.headers["X-Content-Type-Options"] = "nosniff"
		return response

def mount_static_files(app: FastAPI) -> None:
	"""Подключить готовый dist один раз при сборке приложения."""
	app.mount(
		STATIC_URL_PREFIX.rstrip("/"),
		PublicStaticFiles(directory=str(FRONTEND_DIST_DIR), html=False, check_dir=True, follow_symlink=False),
		name="static",
	)