# backend/app/modules/rules/errors.py

"""Ошибки самостоятельных правил без зависимости от HTTP."""


class RuleArticleError(Exception):
	"""Базовая ошибка операций со статьями."""

class RuleArticleNotFound(RuleArticleError):
	"""Статья недоступна либо не существует."""

class RuleArticleConflict(RuleArticleError):
	"""Операция конфликтует с текущим состоянием."""

class InvalidRuleArticle(RuleArticleError):
	"""Недопустимые входные данные."""

class RuleArticleStorageError(RuleArticleError):
	"""Сохранённые данные нарушают контракт."""

class RuleBookError(Exception):
	"""Базовая ошибка операций с книгами."""

class RuleBookNotFound(RuleBookError):
	"""Книга или её публикация недоступна либо не существует."""

class RuleBookConflict(RuleBookError):
	"""Операция конфликтует с текущим состоянием книги."""

class RuleBookDependencyUnavailable(RuleBookConflict):
	"""Публикации статей отсутствуют либо недоступны для операции."""

class InvalidRuleBook(RuleBookError):
	"""Недопустимые входные данные книги."""

class RuleBookStorageError(RuleBookError):
	"""Сохранённые данные книги нарушают контракт."""
