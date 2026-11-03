# backend/app/infrastructure/storage/local_storage.py

"""Локальные файловые операции внутри доверенного корня.

Вызывающий слой согласует доступ к путям и удерживает блокировки
до завершения операции, компенсации или финализации.

Проверки путей не исключают конкурентную подмену другим процессом.
Объект FileReplacement предназначен только для доверенного кода.
"""

from __future__ import annotations
import logging
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4
from backend.app.infrastructure.storage.paths import checked_child, checked_root, inspect_node


log = logging.getLogger(__name__)

@dataclass
class FileReplacement:
	target: Path
	backup: Path | None
	state: str = "pending"

class LocalStorage:
	def __init__(self, root: Path) -> None:
		self._root = checked_root(root)

	@property
	def root(self) -> Path:
		return self._root

	def validate_file(self, path: Path) -> bool:
		"""Проверить обычный файл; вернуть False, если он отсутствует."""
		path = checked_child(self._root, path)
		info = inspect_node(path)

		if info is None:
			return False

		if not stat.S_ISREG(info.st_mode):
			raise ValueError("Для операции с файлом требуется обычный файл")

		return True

	def validate_directory(self, path: Path) -> bool:
		"""Проверить всё дерево до удаления; отсутствующее дерево допустимо."""
		path = checked_child(self._root, path)
		initial = inspect_node(path)

		if initial is None:
			return False

		if not stat.S_ISDIR(initial.st_mode):
			raise ValueError("Для удаления каталога требуется каталог")

		device = initial.st_dev
		pending = [path]

		while pending:
			current = pending.pop()
			info = inspect_node(current)

			if info is None:
				continue

			if info.st_dev != device:
				raise ValueError("Переход на другое файловое устройство при очистке запрещён")

			if stat.S_ISDIR(info.st_mode):
				if os.path.ismount(current):
					raise ValueError("Удаление точки монтирования запрещено")

				with os.scandir(current) as entries:
					pending.extend(current / entry.name for entry in entries)

			elif not stat.S_ISREG(info.st_mode):
				raise ValueError("В очищаемом дереве обнаружен неподдерживаемый тип объекта")

		return True

	def read_file(self, path: Path) -> bytes:
		"""Прочитать обычный файл; отсутствие передать как FileNotFoundError."""
		if not self.validate_file(path):
			raise FileNotFoundError("Файл хранилища не найден")

		return path.read_bytes()

	def create_file(self, path: Path, contents: bytes) -> None:
		"""Создать новый файл без перезаписи существующего."""
		if not isinstance(contents, bytes):
			raise TypeError("Для записи требуются байты")

		path = checked_child(self._root, path)

		if self.validate_file(path):
			raise FileExistsError("Файл хранилища уже существует")

		path.parent.mkdir(parents=True, exist_ok=True)
		checked_child(self._root, path)
		created = False

		try:
			with path.open("xb") as destination:
				created = True

				if destination.write(contents) != len(contents):
					raise OSError("Файл записан не полностью")

				destination.flush()
				os.fsync(destination.fileno())

		except BaseException:
			if created:
				self._discard_temporary(path)

			raise

	def remove_file(self, path: Path) -> None:
		"""Удалить обычный файл; отсутствие допустимо."""
		if not self.validate_file(path):
			return

		path.unlink(missing_ok=True)

	def remove_directory(self, path: Path) -> None:
		"""Удалить проверенное дерево."""
		if not self.validate_directory(path):
			return

		try:
			shutil.rmtree(path)
		except FileNotFoundError:
			if inspect_node(path) is not None:
				raise

	def _discard_temporary(self, path: Path) -> None:
		"""Не подменять исходную ошибку ошибкой удаления временного файла."""
		try:
			self.remove_file(path)
		except (OSError, ValueError):
			log.exception("Не удалось удалить временный файл хранилища %s", path)

	def _check_replacement(self, replacement: FileReplacement) -> None:
		if not isinstance(replacement, FileReplacement):
			raise ValueError("Требуется объект операции замены")

		checked_child(self._root, replacement.target)

		if replacement.state not in {"pending", "rolled_back", "finished"}:
			raise ValueError("Неизвестное состояние операции замены")

		if replacement.backup is None:
			return

		backup = checked_child(self._root, replacement.backup)
		prefix = f"{replacement.target.stem}."
		suffix = ".backup.tmp"

		if backup.parent != replacement.target.parent or not backup.name.startswith(prefix) or not backup.name.endswith(suffix):
			raise ValueError("Резервная копия не соответствует заменённому файлу")

		operation_id = backup.name[len(prefix):-len(suffix)]

		try:
			parsed = UUID(operation_id)
		except ValueError as exc:
			raise ValueError("Некорректный идентификатор резервной копии") from exc

		if str(parsed) != operation_id:
			raise ValueError("Неканонический идентификатор резервной копии")

	def replace_file(self, path: Path, contents: bytes) -> FileReplacement:
		"""Опубликовать новый файл, сохранив прежние байты для компенсации."""
		if not isinstance(contents, bytes):
			raise TypeError("Для записи требуются байты")

		path = checked_child(self._root, path)
		self.validate_file(path)
		operation_id = uuid4()
		temporary = path.with_name(f"{path.stem}.{operation_id}.upload.tmp")
		backup = path.with_name(f"{path.stem}.{operation_id}.backup.tmp")
		temporary_created = False
		backup_created = False

		try:
			self.create_file(temporary, contents)
			temporary_created = True

			try:
				previous = self.read_file(path)
			except FileNotFoundError:
				previous = None

			if previous is not None:
				self.create_file(backup, previous)
				backup_created = True

			replacement = FileReplacement(path, backup if backup_created else None)
			self.validate_file(path)
			checked_child(self._root, temporary)
			os.replace(temporary, path)

		except BaseException:
			if temporary_created:
				self._discard_temporary(temporary)

			if backup_created:
				self._discard_temporary(backup)

			raise

		return replacement

	def rollback_replacement(self, replacement: FileReplacement) -> None:
		"""Восстановить старый файл либо удалить впервые созданный."""
		self._check_replacement(replacement)

		if replacement.state == "rolled_back":
			return

		if replacement.state == "finished":
			raise ValueError("Завершённую замену нельзя откатить")

		if replacement.backup is None:
			self.remove_file(replacement.target)
		else:
			if not self.validate_file(replacement.backup):
				raise FileNotFoundError("Резервная копия изображения не найдена")

			self.validate_file(replacement.target)
			os.replace(replacement.backup, replacement.target)

		replacement.state = "rolled_back"

	def finish_replacement(self, replacement: FileReplacement) -> None:
		"""Удалить резервную копию только после подтверждённого сохранения."""
		self._check_replacement(replacement)

		if replacement.state == "finished":
			return

		if replacement.state == "rolled_back":
			raise ValueError("Отменённую замену нельзя завершить")

		if replacement.backup is not None:
			self.remove_file(replacement.backup)

		replacement.state = "finished"