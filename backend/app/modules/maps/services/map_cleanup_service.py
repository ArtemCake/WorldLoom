# backend/app/modules/maps/services/map_cleanup_service.py

"""Формирование, проверка и выполнение плана очистки карт.

Корень передаёт доверенный серверный код, а не клиент.
build_plan и validate_plan не изменяют файловую систему.

execute_plan удаляет файлы и каталоги. Вызывать его разрешено
только после фиксации удаления игры и задания очистки в БД.

Проверки не блокируют пути и не защищают от всех конкурентных
изменений файловой системы.
"""

from __future__ import annotations
import os
import re
import stat
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from uuid import UUID
from backend.app.infrastructure.storage.local_storage import LocalStorage
from backend.app.modules.maps.services import map_image_service as images


_PLAN_FIELDS = {"root", "game_id", "master_id", "directories", "legacy_map_ids"}
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MISSING = object()

class MapCleanupSource(Protocol):
	id: UUID
	background_storage_path: str | None

def _require_uuid(value: Any, label: str) -> UUID:
	if not isinstance(value, UUID):
		raise ValueError(f"Некорректный идентификатор: {label}")

	return value

def _stored_uuid(value: Any, label: str) -> UUID:
	if not isinstance(value, str):
		raise ValueError(f"Некорректный сохранённый идентификатор: {label}")

	try:
		parsed = UUID(value)
	except ValueError as exc:
		raise ValueError(f"Некорректный сохранённый идентификатор: {label}") from exc

	if str(parsed) != value:
		raise ValueError(f"Требуется канонический UUID: {label}")

	return parsed

def _reject_link(path: Path) -> None:
	try:
		info = os.lstat(path)
	except FileNotFoundError:
		return

	if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
		raise ValueError("Ссылки и точки перенаправления в пути очистки запрещены")

def _checked_root(root: Path) -> Path:
	if not isinstance(root, Path) or not root.is_absolute():
		raise ValueError("Требуется абсолютный путь доверенного корня хранилища")

	for component in (*reversed(root.parents), root):
		_reject_link(component)

	if root.resolve() != root:
		raise ValueError("Корень хранилища не является каноническим путём")

	return root

def _relative_parts(value: Any, length: int) -> tuple[str, ...]:
	if not isinstance(value, str) or not value:
		raise ValueError("Требуется непустой относительный путь")

	path = PurePosixPath(value)

	if path.is_absolute() or "\\" in value or path.as_posix() != value or len(path.parts) != length:
		raise ValueError("Некорректный относительный путь очистки")

	if any(part in {".", ".."} for part in path.parts):
		raise ValueError("Переходы между каталогами в пути очистки запрещены")

	return path.parts

def _directory_parts(relative: str, master_id: UUID, game_id: UUID) -> tuple[str, str]:
	master_folder, game_folder = _relative_parts(relative, 2)

	if not re.fullmatch(r"master-[\w-]+", master_folder) or not re.fullmatch(r"game-[\w-]+", game_folder):
		raise ValueError("Некорректные имена каталогов карт")

	if not master_folder.endswith(f"-{master_id}") or not game_folder.endswith(f"-{game_id}"):
		raise ValueError("Каталог не соответствует мастеру или игре")

	return master_folder, game_folder

def _checked_path(root: Path, parts: tuple[str, ...]) -> Path:
	path = root

	for part in parts:
		path = path / part
		_reject_link(path)

	if not path.resolve().is_relative_to(root):
		raise ValueError("Путь очистки выходит за пределы хранилища")

	return path

def _string_list(value: Any, label: str) -> list[str]:
	if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
		raise ValueError(f"Требуется список строк: {label}")

	return value

def validate_plan(plan: dict[str, Any], *, root: Path) -> tuple[list[Path], list[Path]]:
	"""Проверить весь план без изменения файловой системы."""
	root = _checked_root(root)

	if not isinstance(plan, dict) or set(plan) != _PLAN_FIELDS:
		raise ValueError("Неподдерживаемая структура плана очистки")

	if not isinstance(plan["root"], str) or plan["root"] != str(root):
		raise ValueError("Корень задания не совпадает с доверенным корнем хранилища")

	game_id = _stored_uuid(plan["game_id"], "игра")
	master_id = _stored_uuid(plan["master_id"], "мастер")
	relative_directories = _string_list(plan["directories"], "каталоги")
	legacy_ids = _string_list(plan["legacy_map_ids"], "старые файлы карт")

	directories = [
		_checked_path(root, _directory_parts(relative, master_id, game_id))
		for relative in relative_directories
	]
	legacy_files = [
		_checked_path(root, (f"{_stored_uuid(value, 'карта')}.png",))
		for value in legacy_ids
	]

	return directories, legacy_files

def build_plan(game_id: UUID, master_id: UUID, master_folder: str | None, game_folder: str | None, maps: Iterable[MapCleanupSource], *, root: Path) -> dict[str, Any]:
	"""Подготовить задание из серверных данных игры и её карт."""
	_require_uuid(game_id, "игра")
	_require_uuid(master_id, "мастер")
	root = _checked_root(root)

	if any(value is not None and not isinstance(value, str) for value in (master_folder, game_folder)):
		raise ValueError("Некорректные сохранённые имена каталогов")

	directories: set[str] = set()
	legacy_map_ids: list[str] = []

	if game_folder:
		if not master_folder:
			raise ValueError("Не сохранён каталог мастера")

		relative = f"{master_folder}/{game_folder}"
		_directory_parts(relative, master_id, game_id)
		directories.add(relative)

	for item in maps:
		map_id = _require_uuid(getattr(item, "id", None), "карта")
		key = getattr(item, "background_storage_path", _MISSING)

		if key is _MISSING:
			raise ValueError("В данных карты отсутствует поле пути фона")

		legacy_map_ids.append(str(map_id))

		if key is None or key == "":
			continue

		master_part, game_part, filename = _relative_parts(key, 3)

		if not re.fullmatch(r"map-[1-9][0-9]*\.png", filename):
			raise ValueError("Некорректное имя файла фона карты")

		relative = f"{master_part}/{game_part}"
		_directory_parts(relative, master_id, game_id)
		directories.add(relative)

	plan = {
		"root": str(root),
		"game_id": str(game_id),
		"master_id": str(master_id),
		"directories": sorted(directories),
		"legacy_map_ids": legacy_map_ids,
	}
	validate_plan(plan, root=root)

	return plan

def execute_plan(plan: dict[str, Any], *, root: Path) -> None:
	"""Выполнить очистку после фиксации удаления игры в БД.

	Операция синхронная. Асинхронный вызывающий слой должен
	выполнять её в рабочем потоке, а не в цикле событий.

	Файловое удаление не является транзакционным.
	При ошибке часть объектов уже может отсутствовать.
	Повторное выполнение продолжает очистку.
	"""
	directories, legacy_files = validate_plan(plan, root=root)
	storage = LocalStorage(root)

	for directory in directories:
		storage.validate_directory(directory)

	for path in legacy_files:
		storage.validate_file(path)

	for directory in directories:
		storage.remove_directory(directory)

	for path in legacy_files:
		storage.remove_file(path)

def build_map_cleanup_plan(map_id: UUID, game_id: UUID, master_id: UUID, background_storage_path: str | None, *, root: Path) -> dict:
	"""Подготовить проверяемый план удаления файлов одной карты."""
	if not all(isinstance(value, UUID) for value in (map_id, game_id, master_id)):
		raise ValueError("Для плана очистки требуются UUID карты, игры и мастера")

	plan = {
		"version": 1,
		"root": str(LocalStorage(root).root),
		"map_id": str(map_id),
		"game_id": str(game_id),
		"master_id": str(master_id),
		"background_storage_path": background_storage_path,
	}
	validate_map_cleanup_plan(plan, map_id, game_id, master_id, root=root)
	return plan

def validate_map_cleanup_plan(plan: dict, map_id: UUID, game_id: UUID, master_id: UUID, *, root: Path) -> list[Path]:
	"""Проверить назначение плана и получить только пути файлов этой карты."""
	fields = {"version", "root", "map_id", "game_id", "master_id", "background_storage_path"}

	if not isinstance(plan, dict) or set(plan) != fields:
		raise ValueError("План очистки карты имеет неподдерживаемую структуру")

	if type(plan["version"]) is not int or plan["version"] != 1:
		raise ValueError("Версия плана очистки карты не поддерживается")

	storage = LocalStorage(root)

	if plan["root"] != str(storage.root):
		raise ValueError("Корень хранилища отличается от сохранённого плана")

	for name, expected in (("map_id", map_id), ("game_id", game_id), ("master_id", master_id)):
		if not isinstance(expected, UUID) or plan[name] != str(expected):
			raise ValueError("План очистки относится к другой карте, игре или владельцу")

	paths = []
	key = plan["background_storage_path"]

	if key is not None:
		if not isinstance(key, str) or not key:
			raise ValueError("В плане сохранён некорректный адрес фона")

		path = images.image_path(key, root=root)
		master_folder, game_folder, filename = PurePosixPath(key).parts

		if not master_folder.endswith(f"-{master_id}") or not game_folder.endswith(f"-{game_id}"):
			raise ValueError("Адрес фона не соответствует владельцу или игре")

		paths.append(path)

	paths.append(images.image_path(map_id, root=root))
	return paths

def execute_map_cleanup_plan(plan: dict, map_id: UUID, game_id: UUID, master_id: UUID, *, root: Path) -> None:
	"""Удалить только файлы карты, не затрагивая каталоги и соседние изображения."""
	paths = validate_map_cleanup_plan(plan, map_id, game_id, master_id, root=root)
	storage = LocalStorage(root)

	for path in paths:
		storage.validate_file(path)

	for path in paths:
		storage.remove_file(path)