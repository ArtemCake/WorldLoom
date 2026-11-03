# backend/app/infrastructure/storage/paths.py

"""Проверка путей локального хранилища.

Проверки не создают и не изменяют файлы.
Проверки не блокируют файловую систему.
"""

from __future__ import annotations
import os
import stat
from pathlib import Path


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

def inspect_node(path: Path) -> os.stat_result | None:
	"""Прочитать сведения об объекте, не переходя по конечной ссылке."""
	try:
		info = os.lstat(path)
	except FileNotFoundError:
		return None

	if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
		raise ValueError("Ссылки и точки перенаправления в хранилище запрещены")

	return info

def checked_root(root: Path) -> Path:
	"""Проверить абсолютный канонический корень и его родителей."""
	if not isinstance(root, Path) or not root.is_absolute():
		raise ValueError("Требуется абсолютный путь корня хранилища")

	if root == Path(root.anchor):
		raise ValueError("Корень файловой системы нельзя использовать как корень очистки")

	for component in (*reversed(root.parents), root):
		info = inspect_node(component)

		if info is not None and not stat.S_ISDIR(info.st_mode):
			raise ValueError("Корень хранилища и его родители должны быть каталогами")

	if root.resolve() != root:
		raise ValueError("Корень хранилища не является каноническим путём")

	return root

def checked_child(root: Path, path: Path) -> Path:
	"""Проверить вложенный путь, не разрешая операцию над самим корнем."""
	root = checked_root(root)

	if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
		raise ValueError("Требуется абсолютный путь внутри хранилища")

	try:
		relative = path.relative_to(root)
	except ValueError as exc:
		raise ValueError("Путь выходит за пределы хранилища") from exc

	if not relative.parts:
		raise ValueError("Операция над корнем хранилища запрещена")

	current = root

	for index, part in enumerate(relative.parts):
		current = current / part
		info = inspect_node(current)

		if info is not None and index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
			raise ValueError("Промежуточный компонент пути не является каталогом")

	if path.resolve() != path:
		raise ValueError("Путь хранилища не является каноническим")

	return path