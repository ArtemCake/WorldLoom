# backend/app/core/map_storage.py

"""Общий корень изображений карт для HTTP-операций и фоновой очистки."""

from pathlib import Path
from backend.app.core.settings import WebAppSettings


def get_map_images_root(settings: WebAppSettings) -> Path:
	"""Разрешить относительный путь от корня проекта без создания каталогов."""
	configured = settings.MAP_IMAGES_DIR

	if configured is None:
		raise RuntimeError("Для хранения изображений карт необходимо задать MAP_IMAGES_DIR")

	project_root = Path(settings.BASE_DIR).resolve()
	root = Path(configured)

	if not root.is_absolute():
		root = project_root / root

	root = root.resolve()

	if root == project_root or project_root.is_relative_to(root):
		raise RuntimeError("Хранилище карт не должно совпадать с корнем проекта или содержать его")

	for relative in ("frontend/public", "frontend/dist"):
		public_root = (project_root / relative).resolve()

		if root.is_relative_to(public_root) or public_root.is_relative_to(root):
			raise RuntimeError("Хранилище карт не должно пересекаться с публичными каталогами")

	return root