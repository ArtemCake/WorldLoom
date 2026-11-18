# backend/app/modules/game_systems/schemas/system_book_set.py

"""Книжная часть комплекта системы с закреплением конкретных публикаций."""

from typing import Literal
from pydantic import Field, model_validator
from backend.app.modules.game_systems.schemas.game_rules import RulesModel, TransportUUID


class SystemBookPin(RulesModel):
	"""Одна книга и явно выбранная публикация этой книги."""

	book_id: TransportUUID
	version_id: TransportUUID

class SystemBookSet(RulesModel):
	"""Упорядоченный состав книг без автоматического выбора последних версий."""

	schema_version: Literal[1] = 1
	books: list[SystemBookPin] = Field(default_factory=list)

	@model_validator(mode="after")
	def validate_unique_books(self):
		book_ids = [item.book_id for item in self.books]
		version_ids = [item.version_id for item in self.books]

		if len(book_ids) != len(set(book_ids)):
			raise ValueError("Одна книга не может входить в комплект несколько раз")

		if len(version_ids) != len(set(version_ids)):
			raise ValueError("Одна публикация не может быть назначена нескольким книгам")

		return self
