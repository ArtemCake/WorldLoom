# backend/app/modules/maps/services/map_image_service.py

"""Проверка загрузки и нормализация фонового изображения карты.

Модуль не назначает адреса, не обращается к БД и не изменяет хранилище.
Ограничения передаёт доверенный серверный код.

Запись, чтение, замена и восстановление файлов переносятся отдельно.
"""

from __future__ import annotations
import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Protocol, TypeVar
from uuid import UUID
from PIL import Image, ImageOps, UnidentifiedImageError
from backend.app.infrastructure.storage.local_storage import FileReplacement, LocalStorage
from backend.app.infrastructure.storage.paths import checked_child
from backend.app.modules.maps.errors import InvalidMapImage, InvalidMapImageKey, MapImageNotFound, MapImageStorageFailure, MapImageTooLarge


log = logging.getLogger(__name__)
T = TypeVar("T")

class BackgroundUpload(Protocol):
	async def read(self, size: int = -1) -> bytes:
		...

	async def close(self) -> None:
		...

@dataclass(frozen=True)
class ImageLimits:
	max_bytes: int
	max_side: int
	max_pixels: int

	def __post_init__(self) -> None:
		for name in ("max_bytes", "max_side", "max_pixels"):
			value = getattr(self, name)

			if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
				raise ValueError(f"Требуется положительное целое ограничение: {name}")

def normalize_image(contents: bytes, *, limits: ImageLimits) -> bytes:
	"""Проверить исходные байты и получить PNG без исходных метаданных."""
	if not isinstance(contents, bytes):
		raise InvalidMapImage("Требуются байты изображения")

	if not contents:
		raise InvalidMapImage("Выбран пустой файл")

	if len(contents) > limits.max_bytes:
		raise MapImageTooLarge("Изображение превышает допустимый размер загрузки")

	try:
		with Image.open(BytesIO(contents), formats=["JPEG", "PNG", "WEBP"]) as source:
			width, height = source.size

			if width <= 0 or height <= 0 or width > limits.max_side or height > limits.max_side or width * height > limits.max_pixels:
				raise InvalidMapImage("Слишком большие размеры изображения")

			if getattr(source, "n_frames", 1) != 1:
				raise InvalidMapImage("Выберите изображение без анимации")

			source.load()

			with ImageOps.exif_transpose(source) as oriented:
				has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
				mode = "RGBA" if has_alpha else "RGB"

				with oriented.convert(mode) as converted:
					with Image.new(mode, converted.size) as clean:
						clean.paste(converted)

						with BytesIO() as output:
							clean.save(output, format="PNG")
							return output.getvalue()

	except InvalidMapImage:
		raise
	except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError, SyntaxError) as exc:
		raise InvalidMapImage("Не удалось прочитать изображение. Выберите PNG, JPEG или WebP") from exc

async def prepare_background(upload: BackgroundUpload, *, limits: ImageLimits) -> bytes:
	"""Прочитать ограниченный объём, закрыть загрузку и подготовить PNG."""
	try:
		contents = await upload.read(limits.max_bytes + 1)
	finally:
		await upload.close()

	return await asyncio.to_thread(normalize_image, contents, limits=limits)

def image_path(image_key: UUID | str, *, root: Path) -> Path:
	"""Получить проверенный путь; права пользователя здесь не проверяются."""
	if isinstance(image_key, UUID):
		parts = (f"{image_key}.png",)

	elif isinstance(image_key, str):
		relative = PurePosixPath(image_key)

		if relative.is_absolute() or "\\" in image_key or relative.as_posix() != image_key or len(relative.parts) != 3:
			raise InvalidMapImageKey("Некорректный адрес изображения карты")

		master_folder, game_folder, filename = relative.parts

		if (
				not re.fullmatch(r"master-[\w-]+", master_folder)
				or not re.fullmatch(r"game-[\w-]+", game_folder)
				or not re.fullmatch(r"map-[1-9][0-9]*\.png", filename)
		):
			raise InvalidMapImageKey("Некорректный адрес изображения карты")

		parts = relative.parts

	else:
		raise InvalidMapImageKey("Для изображения требуется UUID или относительный адрес")

	try:
		storage = LocalStorage(root)
		return checked_child(storage.root, storage.root.joinpath(*parts))
	except ValueError as exc:
		raise InvalidMapImageKey("Недопустимый путь изображения карты") from exc

async def _wait_file_task(task: asyncio.Task[T]) -> tuple[T, bool]:
	"""Дождаться потока, запомнив отмену ожидания."""
	cancelled = False

	while True:
		try:
			return await asyncio.shield(task), cancelled
		except asyncio.CancelledError:
			if task.cancelled():
				raise

			cancelled = True
		except Exception:
			if cancelled:
				log.exception("Файловая операция завершилась ошибкой после запроса отмены")

			raise

async def _run_file_change(operation: Callable[[], T], *, compensate: Callable[[T], None] | None = None) -> T:
	"""Не освобождать вызывающий слой до окончания изменения и компенсации."""
	task = asyncio.create_task(asyncio.to_thread(operation))
	result, cancelled = await _wait_file_task(task)

	if cancelled:
		if compensate is not None:
			compensation = asyncio.create_task(asyncio.to_thread(compensate, result))

			try:
				await _wait_file_task(compensation)
			except Exception:
				log.exception("Не удалось компенсировать файловое изменение после отмены")
				raise

		raise asyncio.CancelledError()

	return result

def _save_background(image_key: UUID | str, contents: bytes, *, root: Path) -> None:
	path = image_path(image_key, root=root)

	try:
		LocalStorage(root).create_file(path, contents)
	except ValueError as exc:
		raise InvalidMapImageKey("Недопустимый путь изображения карты") from exc

async def save_background(image_key: UUID | str, contents: bytes, *, root: Path) -> None:
	"""Создать файл; при отмене во время ожидания компенсировать создание."""
	try:
		await _run_file_change(
			lambda: _save_background(image_key, contents, root=root),
			compensate=lambda _: _remove_background(image_key, root=root),
		)
	except OSError as exc:
		raise MapImageStorageFailure("Не удалось сохранить изображение карты") from exc

def _read_background(image_key: UUID | str, *, root: Path) -> bytes:
	path = image_path(image_key, root=root)

	try:
		return LocalStorage(root).read_file(path)
	except ValueError as exc:
		raise InvalidMapImageKey("Недопустимый путь изображения карты") from exc

async def read_background(image_key: UUID | str, *, root: Path) -> bytes:
	"""Прочитать изображение; отсутствие отличать от ошибки хранилища."""
	try:
		return await asyncio.to_thread(_read_background, image_key, root=root)
	except FileNotFoundError as exc:
		raise MapImageNotFound("Изображение карты не найдено") from exc
	except OSError as exc:
		raise MapImageStorageFailure("Не удалось прочитать изображение карты") from exc

def _remove_background(image_key: UUID | str, *, root: Path) -> None:
	path = image_path(image_key, root=root)

	try:
		LocalStorage(root).remove_file(path)
	except ValueError as exc:
		raise InvalidMapImageKey("Недопустимый путь изображения карты") from exc

async def remove_background(image_key: UUID | str, *, root: Path) -> None:
	"""Дождаться удаления; ошибки доступа журналировать, как в исходнике."""
	try:
		await _run_file_change(lambda: _remove_background(image_key, root=root))
	except OSError:
		log.exception("Не удалось очистить файл фона карты %s", image_key)

async def replace_background(image_key: UUID | str, contents: bytes, *, root: Path) -> FileReplacement:
	"""Заменить фон; вернуть объект для отката или завершения."""
	try:
		path = image_path(image_key, root=root)
		storage = LocalStorage(root)
		return await _run_file_change(
			lambda: storage.replace_file(path, contents),
			compensate=storage.rollback_replacement,
		)
	except ValueError as exc:
		raise InvalidMapImageKey("Недопустимый путь или состояние замены изображения") from exc
	except OSError as exc:
		raise MapImageStorageFailure("Не удалось заменить изображение карты или восстановить его после отмены") from exc

async def rollback_background(replacement: FileReplacement, *, root: Path) -> None:
	"""Восстановить прежний фон; при ошибке сохранить резервную копию."""
	try:
		storage = LocalStorage(root)
		await _run_file_change(lambda: storage.rollback_replacement(replacement))
	except ValueError as exc:
		raise InvalidMapImageKey("Недопустимый путь или состояние восстановления изображения") from exc
	except OSError as exc:
		log.exception("Не удалось восстановить фон; резервная копия: %s", replacement.backup)
		raise MapImageStorageFailure("Не удалось восстановить прежний фон. Требуется проверка хранилища") from exc

async def finish_background_replacement(replacement: FileReplacement, *, root: Path) -> None:
	"""Удалить резервную копию после commit; ошибку доступа журналировать."""
	try:
		storage = LocalStorage(root)
		await _run_file_change(lambda: storage.finish_replacement(replacement))
	except ValueError as exc:
		raise InvalidMapImageKey("Недопустимый путь или состояние завершения замены") from exc
	except OSError:
		log.exception("Не удалось удалить резервную копию фона: %s", replacement.backup)