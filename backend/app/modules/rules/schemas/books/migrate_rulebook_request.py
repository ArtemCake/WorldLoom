"""Request-схема для HTTP-оркестрации migrate_system_rulebook."""

from __future__ import annotations

from pydantic import Field, field_validator

from backend.app.modules.rules.schemas.articles import RulesContentModel, Title


class MigrateRulebookRequest(RulesContentModel):
    """Ввод переноса системного правила в книгу.

    title — заголовок итоговой книги; при отсутствии берётся из
    ``game_system.name`` вызывающим слоем. Остальные поля уходят прямо в
    ``migrate_system_rulebook`` и в ``BookDraftContent``.
    """

    title: Title | None = None
    summary: str = Field(default="", strict=True, max_length=5000)
    language: str = Field(default="ru", strict=True, min_length=2, max_length=20)
    edition_key: str | None = Field(default=None, strict=True, min_length=1, max_length=100)

    @field_validator("title", "language", "edition_key")
    @classmethod
    def validate_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Значение не может состоять из пробелов")
        return value
