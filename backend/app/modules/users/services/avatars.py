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
from urllib.parse import quote, unquote
from uuid import UUID, uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from backend.app.core.logging import get_logger
from backend.app.core.paths import UPLOADS_DIR
from backend.app.core.settings import WebAppSettings
from backend.app.modules.users.errors import AvatarTooLarge, InvalidAvatar


log = get_logger(__name__)

AVATARS_ROOT = UPLOADS_DIR / "private" / "avatars"

# Адрес выдаётся маршрутом /profile/avatars: каталог private закрыт
# для статической раздачи, поэтому путь к файлу не может быть адресом.
AVATAR_URL_PREFIX = "/profile/avatars"
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# Имя файла формирует только сервер: никнейм и два hex-отпечатка uuid4.
_AVATAR_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CATALOG_TAIL = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_BAD_ADDRESS = "Некорректный адрес аватара"

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

def _avatar_catalog(nickname: str, user_id: UUID) -> str:
	"""Собрать имя каталога пользователя: никнейм и его идентификатор."""
	return f"{nickname}_{user_id}"

def _split_catalog(catalog: str) -> tuple[str, UUID]:
	"""Разобрать каталог на никнейм и идентификатор владельца."""
	if not isinstance(catalog, str) or catalog in (".", "..") or catalog != Path(catalog).name:
		raise ValueError(_BAD_ADDRESS)

	nickname, _, tail = catalog.rpartition("_")

	if not nickname or _CATALOG_TAIL.fullmatch(tail) is None:
		raise ValueError(_BAD_ADDRESS)

	try:
		return nickname, UUID(tail)
	except ValueError:
		raise ValueError(_BAD_ADDRESS) from None

def _checked_avatar_path(catalog: str, filename: str) -> Path:
	"""Разрешить только серверное имя PNG внутри каталога его владельца."""
	nickname, _ = _split_catalog(catalog)

	if not isinstance(filename, str) or filename != Path(filename).name:
		raise ValueError(_BAD_ADDRESS)

	prefix, suffix = f"{nickname}_", ".png"

	if not filename.startswith(prefix) or not filename.endswith(suffix):
		raise ValueError(_BAD_ADDRESS)

	digest = filename[len(prefix):-len(suffix)]

	if _AVATAR_DIGEST.fullmatch(digest) is None:
		raise ValueError(_BAD_ADDRESS)

	path = AVATARS_ROOT / catalog / filename

	for component in (*reversed(path.parents), path):
		try:
			info = os.lstat(component)
		except FileNotFoundError:
			continue

		if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
			raise ValueError("Ссылки и точки перенаправления в хранилище аватаров запрещены")

	return path

def _split_avatar_url(url: str) -> tuple[str, str] | None:
	"""Выделить каталог и имя файла из любого адреса вида .../avatars/<каталог>/<имя>."""
	if not isinstance(url, str) or not url:
		return None

	_, separator, tail = url.rpartition("/avatars/")

	if not separator:
		return None

	catalog, slash, filename = tail.partition("/")

	if not slash or not catalog or not filename:
		return None

	return unquote(catalog), unquote(filename)

def normalize_avatar_url(url: str | None) -> str | None:
	"""Преобразовать старый адрес в путь маршрута выдачи.

	Адреса прежней формы (например ``frontend/uploads/private/avatars/...``
	или ``profile/avatars/...``) приводят к виду ``/profile/avatars/<каталог>/<имя>``
	через ``_split_avatar_url`` и ``quote``.  Если разобрать адрес нельзя —
	возвращает исходное значение (оно не переписывается в БД).
	"""
	target = _split_avatar_url(url)

	if target is None:
		return url if isinstance(url, str) and url else None

	catalog, filename = target

	try:
		_checked_avatar_path(catalog, filename)
	except ValueError:
		return None

	return (
		f"{AVATAR_URL_PREFIX}"
		f"/{quote(catalog, safe='')}"
		f"/{quote(filename, safe='')}"
	)

def save_avatar(nickname, user_id: UUID, contents: bytes) -> str:
	"""Записать подготовленный PNG под новым именем, не заменяя существующий файл."""
	catalog = _avatar_catalog(nickname, user_id)
	filename = f"{nickname}_{uuid4().hex}{uuid4().hex}.png"
	path = _checked_avatar_path(catalog, filename)
	path.parent.mkdir(parents=True, exist_ok=True)
	path = _checked_avatar_path(catalog, filename)
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

	return (
		f"{AVATAR_URL_PREFIX}"
		f"/{quote(catalog, safe='')}"
		f"/{quote(filename, safe='')}"
	)

def remove_owned_avatar(url: str | None, user_id: UUID) -> None:
	"""Удалить только управляемый файл этого пользователя; прочие адреса не трогать."""
	target = _split_avatar_url(url)

	if target is None:
		return

	catalog, filename = target

	try:
		# Никнейм брался из адреса: он мог измениться после сохранения файла,
		# а владелец определяется идентификатором из имени каталога.
		_, owner = _split_catalog(catalog)

		if owner != user_id:
			return

		path = _checked_avatar_path(catalog, filename)
		path.unlink(missing_ok=True)
	except (OSError, ValueError):
		log.warning("Не удалось очистить заменённый файл аватара.")

def get_avatar_path(catalog: str, filename: str) -> Path:
	"""Получить проверенный путь для HTTP-выдачи."""
	path = _checked_avatar_path(catalog, filename)
	if not path.is_file():
		raise FileNotFoundError("Аватар не найден")
	return path