# backend/app/modules/admin/schemas.py

"""Допустимые значения административных запросов."""

from enum import StrEnum


class ReportStatus(StrEnum):
	NEW = "new"
	IN_REVIEW = "in_review"
	RESOLVED = "resolved"
	DISMISSED = "dismissed"