# backend/app/modules/game_systems/services/system_book_commands.py

"""Команды книжного состава без записи в БД и проверки прав доступа."""

from uuid import UUID
from backend.app.modules.game_systems.schemas.system_book_set import SystemBookPin, SystemBookSet


def _identifier(value: UUID) -> UUID:
	if not isinstance(value, UUID):
		raise TypeError("Требуется идентификатор UUID")

	return value

def _payload(value: SystemBookSet) -> dict:
	if not isinstance(value, SystemBookSet):
		raise TypeError("Требуется книжный состав системы")

	checked = SystemBookSet.model_validate(value.model_dump(mode="python"))
	return checked.model_dump(mode="python")

def _pin_payload(value: SystemBookPin) -> dict:
	if not isinstance(value, SystemBookPin):
		raise TypeError("Требуется закреплённая публикация книги")

	checked = SystemBookPin.model_validate(value.model_dump(mode="python"))
	return checked.model_dump(mode="python")

def _index(books: list[dict], book_id: UUID) -> int:
	_identifier(book_id)

	for index, item in enumerate(books):
		if item["book_id"] == book_id:
			return index

	raise ValueError("Книга не включена в комплект")

def _expect_version(item: dict, expected_version_id: UUID) -> None:
	_identifier(expected_version_id)

	if item["version_id"] != expected_version_id:
		raise ValueError("Закреплённая публикация изменилась. Получите актуальный состав")

def add_system_book(value: SystemBookSet, pin: SystemBookPin) -> SystemBookSet:
	"""Добавить новую книгу в конец состава."""

	payload = _payload(value)
	candidate = _pin_payload(pin)

	if any(item["book_id"] == candidate["book_id"] for item in payload["books"]):
		raise ValueError("Книга уже включена. Для обновления выберите другую публикацию явно")

	payload["books"].append(candidate)
	return SystemBookSet.model_validate(payload)

def replace_system_book(value: SystemBookSet, pin: SystemBookPin, expected_version_id: UUID) -> SystemBookSet:
	"""Заменить публикацию книги, сохранив её место в составе."""

	payload = _payload(value)
	candidate = _pin_payload(pin)
	index = _index(payload["books"], candidate["book_id"])

	_expect_version(payload["books"][index], expected_version_id)

	payload["books"][index] = candidate
	return SystemBookSet.model_validate(payload)

def remove_system_book(value: SystemBookSet, book_id: UUID, expected_version_id: UUID) -> SystemBookSet:
	"""Удалить вхождение из состава, не удаляя книгу и её публикации."""

	payload = _payload(value)
	index = _index(payload["books"], book_id)

	_expect_version(payload["books"][index], expected_version_id)

	payload["books"].pop(index)
	return SystemBookSet.model_validate(payload)

def move_system_book(value: SystemBookSet, book_id: UUID, before_book_id: UUID | None) -> SystemBookSet:
	"""Перенести книгу перед другой книгой; None означает конец списка."""

	payload = _payload(value)
	books = payload["books"]
	source_index = _index(books, book_id)

	if before_book_id is not None:
		_index(books, before_book_id)

	if book_id == before_book_id:
		return SystemBookSet.model_validate(payload)

	item = books.pop(source_index)
	destination = len(books) if before_book_id is None else _index(books, before_book_id)

	books.insert(destination, item)
	return SystemBookSet.model_validate(payload)
