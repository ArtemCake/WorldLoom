# backend/app/modules/users/services/avatars.py

"""Проверка аватаров и хранение новых файлов отдельно от исходников frontend."""

from __future__ import annotations
import asyncio
import os
import re
import stat
from io import BytesIO
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from backend.app.core.logging import get_logger
from backend.app.core.paths import DATA_DIR
from backend.app.core.settings import WebAppSettings
from backend.app.modules.users.errors import AvatarTooLarge, InvalidAvatar


log = get_logger(__name__)

AVATARS_ROOT = DATA_DIR / "avatars"
AVATAR_URL_PREFIX = "/profile/avatars/"
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

class AvatarUpload(Protocol):
	filename: str | None

	async def read(self, size: int = -1) -> bytes:
		...

def _normalize_avatar(contents: bytes, settings: WebAppSettings) -> bytes:
	"""Проверить реальные байты изображения и подготовить статичный PNG."""
	if not contents:
		raise InvalidAvatar("Выбран пустой файл аватара.")

	if len(contents) > settings.AVATAR_MAX_BYTES:
		raise AvatarTooLarge()

	try:
		with Image.open(BytesIO(contents), formats=["JPEG", "PNG", "WEBP"]) as source:
			width, height = source.size
			if min(width, height) <= 0 or max(width, height) > settings.AVATAR_MAX_SIDE:
				raise InvalidAvatar("Слишком большие размеры изображения.")

			if width * height > settings.AVATAR_MAX_PIXELS:
				raise InvalidAvatar("Изображение содержит слишком много пикселей.")

			if getattr(source, "n_frames", 1) != 1:
				raise InvalidAvatar("Для аватара выберите изображение без анимации.")

			source.load()

			with ImageOps.exif_transpose(source) as oriented:
				with oriented.convert("RGBA") as converted:
					converted.thumbnail((settings.AVATAR_OUTPUT_SIDE, settings.AVATAR_OUTPUT_SIDE), Image.Resampling.LANCZOS)

					# Новое изображение не наследует EXIF, комментарии и прочие исходные метаданные.
					with Image.new("RGBA", converted.size) as clean:
						clean.paste(converted)
						output = BytesIO()
						clean.save(output, format="PNG")

		normalized = output.getvalue()
		if len(normalized) > settings.AVATAR_MAX_BYTES:
			raise AvatarTooLarge("Подготовленный аватар превышает допустимый размер.")

		return normalized
	except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
		raise InvalidAvatar("Выберите корректное изображение JPEG, PNG или WebP.") from exc

async def prepare_avatar(upload: AvatarUpload | None, *, settings: WebAppSettings) -> bytes | None:
	"""Ограничить чтение загрузки; обработку изображения выполнять вне цикла событий."""
	if upload is None or not upload.filename:
		return None

	contents = await upload.read(settings.AVATAR_MAX_BYTES + 1)
	if len(contents) > settings.AVATAR_MAX_BYTES:
		raise AvatarTooLarge()

	return await asyncio.to_thread(_normalize_avatar, contents, settings)

def _checked_avatar_path(user_id: UUID, filename: str) -> Path:
	"""Разрешить только серверное имя PNG внутри каталога указанного пользователя."""
	if not isinstance(user_id, UUID) or re.fullmatch(r"[0-9a-f]{32}\.png", filename) is None:
		raise ValueError("Некорректный адрес аватара")

	path = AVATARS_ROOT / str(user_id) / filename

	for component in (*reversed(path.parents), path):
		try:
			info = os.lstat(component)
		except FileNotFoundError:
			continue

		if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
			raise ValueError("Ссылки и точки перенаправления в хранилище аватаров запрещены")

	return path

def save_avatar(user_id: UUID, contents: bytes) -> str:
	"""Записать подготовленный PNG под новым именем, не заменяя существующий файл."""
	filename = f"{uuid4().hex}.png"
	path = _checked_avatar_path(user_id, filename)
	path.parent.mkdir(parents=True, exist_ok=True)
	path = _checked_avatar_path(user_id, filename)
	created = False

	try:
		with path.open("xb") as output:
			created = True
			output.write(contents)
	except OSError:
		if created:
			try:
				path.unlink(missing_ok=True)
			except OSError:
				log.warning("Не удалось убрать незавершённый файл аватара.")
		raise

	return f"{AVATAR_URL_PREFIX}{user_id}/{filename}"

def remove_owned_avatar(url: str | None, user_id: UUID) -> None:
	"""Удалить только новый управляемый файл этого пользователя; старые адреса не трогать."""
	prefix = f"{AVATAR_URL_PREFIX}{user_id}/"
	if not isinstance(url, str) or not url.startswith(prefix):
		return

	try:
		path = _checked_avatar_path(user_id, url[len(prefix):])
		path.unlink(missing_ok=True)
	except (OSError, ValueError):
		log.warning("Не удалось очистить заменённый файл аватара.")

def get_avatar_path(user_id: UUID, filename: str) -> Path:
	"""Получить проверенный путь для HTTP-выдачи."""
	path = _checked_avatar_path(user_id, filename)
	if not path.is_file():
		raise FileNotFoundError("Аватар не найден")
	return path