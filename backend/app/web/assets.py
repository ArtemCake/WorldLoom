# backend/app/web/assets.py

"""Адреса публичных ресурсов и совместимость шаблонов с manifest Vite."""

import base64
import json
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from backend.app.core.paths import VITE_MANIFEST_FILE


PUBLIC_URL_PREFIX = "/frontend/public/"

_ENTRY_ALIASES = {
	"js/main.min.js": ("src/js/main.js", ".js"),
	"css/style.min.css": ("src/styles/style.scss", ".css"),
}

def _relative_asset_name(value: object) -> str:
	"""Проверить значение извне и вернуть нормализованный относительный путь."""
	if not isinstance(value, str) or not value:
		raise ValueError("Требуется непустой путь ресурса")

	if any(ord(character) < 32 or ord(character) == 127 for character in value):
		raise ValueError("Управляющие символы в пути ресурса запрещены")

	if any(character in value for character in ("\\", "?", "#", ":", "%")):
		raise ValueError("Недопустимые символы в пути ресурса")

	path = PurePosixPath(value)

	if not path.parts or path.is_absolute() or path.as_posix() != value:
		raise ValueError("Требуется нормализованный относительный путь ресурса")

	if any(part.startswith(".") or part == "private" for part in path.parts):
		raise ValueError("Этот каталог не предназначен для публичной выдачи")

	return value

def static_url(filename: str) -> str:
	"""Сформировать адрес обычного публичного ресурса без чтения manifest."""
	relative = _relative_asset_name(filename)
	return f"{PUBLIC_URL_PREFIX}{quote(relative, safe='/')}"

def create_static_url(manifest_file: Path = VITE_MANIFEST_FILE) -> Callable[[str], str]:
	"""Прочитать manifest один раз при создании окружения HTML-шаблонов."""
	try:
		manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
	except (OSError, ValueError) as exc:
		raise RuntimeError("Не удалось прочитать manifest frontend. Сначала выполните npm run build.") from exc

	if not isinstance(manifest, dict):
		raise RuntimeError("Manifest frontend должен содержать объект")

	dist_root = manifest_file.parent.parent.resolve()
	aliases: dict[str, str] = {}

	for legacy_name, (entry_name, extension) in _ENTRY_ALIASES.items():
		entry = manifest.get(entry_name)

		if not isinstance(entry, dict):
			raise RuntimeError(f"В manifest frontend отсутствует точка входа: {entry_name}")

		try:
			relative = _relative_asset_name(entry.get("file"))
		except ValueError as exc:
			raise RuntimeError(f"Некорректный путь точки входа frontend: {entry_name}") from exc

		target = (dist_root / relative).resolve()

		if not target.is_relative_to(dist_root) or target.suffix != extension or not target.is_file():
			raise RuntimeError(f"Не найден корректный результат сборки frontend: {entry_name}")

		aliases[legacy_name] = relative

	def resolve_url(filename: str) -> str:
		relative = _relative_asset_name(filename)
		return static_url(aliases.get(relative, relative))

	return resolve_url

def b64encode_filter(value: bytes) -> str:
	"""Сохранить кодирование двоичных значений для существующих шаблонов."""
	return base64.b64encode(value).decode("utf-8")