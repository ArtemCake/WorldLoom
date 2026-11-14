# backend/app/modules/rules/services/books/book_draft_commands.py

"""Преобразования общего книжного черновика без записи в БД."""

from copy import deepcopy
from backend.app.modules.rules.schemas.books import book_draft_content as contracts
from backend.app.modules.rules.schemas.books.books import BookContent

_COMMANDS = (contracts.AddBookText, contracts.UpdateBookText, contracts.RemoveBookText)

def read_book_draft_content(value: BookContent | dict) -> contracts.BookDraftContent:
	"""Прочитать новый формат либо явно преобразовать содержание прежнего формата."""

	if isinstance(value, BookContent):
		payload = value.model_dump(mode="python")
	elif isinstance(value, dict):
		payload = deepcopy(value)
	else:
		raise TypeError("Передано неподдерживаемое содержание книги")

	version = payload.get("schema_version")

	if type(version) is not int:
		raise ValueError("Версия содержания должна быть указана целым числом")

	if version == 1:
		previous = BookContent.model_validate(payload)
		payload = previous.model_dump(mode="python")
		payload["schema_version"] = 2
	elif version != 2:
		raise ValueError("Неподдерживаемая версия содержания книги")

	return contracts.BookDraftContent.model_validate(payload)

def _checked_command(command):
	for model in _COMMANDS:
		if isinstance(command, model):
			return model.model_validate(command.model_dump(mode="python"))

	raise TypeError("Передана неподдерживаемая команда собственного текста")

def apply_book_text_command(value: BookContent | dict, command) -> contracts.BookDraftContent:
	"""Вернуть новый проверенный черновик, не изменяя входные объекты."""

	content = read_book_draft_content(value)
	command = _checked_command(command)
	payload = content.model_dump(mode="python")
	toc = payload["toc"]

	if isinstance(command, contracts.AddBookText):
		if any(node["key"] == command.node.key for node in toc):
			raise ValueError("Ключ пункта оглавления уже занят")

		toc.append(command.node.model_dump(mode="python"))
	else:
		index = next((index for index, node in enumerate(toc) if node["key"] == command.key), None)

		if index is None:
			raise ValueError("Собственный текст не найден")

		if toc[index]["kind"] != "text":
			raise ValueError("Эта операция разрешена только для собственного текста книги")

		if isinstance(command, contracts.UpdateBookText):
			toc[index]["content"] = command.content.model_dump(mode="python")
		else:
			del toc[index]

	return contracts.BookDraftContent.model_validate(payload)