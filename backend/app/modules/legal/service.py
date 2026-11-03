# backend/app/modules/legal/service.py

"""Чтение доверенных юридических HTML-фрагментов из исходников проекта."""

from dataclasses import dataclass
import markdown
from backend.app.core.paths import LEGAL_CONTENT_DIR


_DOCUMENTS = {
	"cookie-policy": ("cookie_policy.md", "Политика использования cookie"),
	"privacy-policy": ("privacy_policy.md", "Политика конфиденциальности"),
	"terms": ("terms_of_service.md", "Пользовательское соглашение"),
}

class LegalDocumentUnavailable(RuntimeError):
	"""Не удалось прочитать настроенный документ проекта."""

@dataclass(frozen=True, slots=True)
class LegalDocument:
	title: str
	content: str

def load_legal_document(document_key: str) -> LegalDocument:
	"""Загрузить только документ из фиксированного списка без выполнения шаблонов."""
	if document_key not in _DOCUMENTS:
		raise ValueError("Неизвестный юридический документ.")

	filename, title = _DOCUMENTS[document_key]

	try:
		root = LEGAL_CONTENT_DIR.resolve(strict=True)
		path = (root / filename).resolve(strict=True)

		if not path.is_relative_to(root) or not path.is_file():
			raise LegalDocumentUnavailable("Некорректный путь юридического документа.")

		content = path.read_text(encoding="utf-8")
	except (OSError, UnicodeError, RuntimeError) as exc:
		raise LegalDocumentUnavailable("Не удалось прочитать юридический документ.") from exc

	if not content.strip():
		raise LegalDocumentUnavailable("Юридический документ пуст.")

	return LegalDocument(title=title, content=markdown.markdown(content, extensions=["tables", "sane_lists"]))