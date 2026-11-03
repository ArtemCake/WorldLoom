# backend/app/web/security_headers.py

"""Защитные HTTP-заголовки без зависимости от настроек приложения."""

from __future__ import annotations


CONTENT_SECURITY_POLICY = " ".join((
	"default-src 'self';",
	"script-src 'self' https://cdn.jsdelivr.net https://unpkg.com;",
	"style-src 'self' 'unsafe-inline';",
	"img-src 'self' data: blob:;",
	"connect-src 'self';",
	"frame-ancestors 'none';",
))

def build_security_headers(*, production: bool) -> dict[str, str]:
	"""Собрать отдельный набор заголовков для экземпляра middleware."""
	headers = {
		"X-Content-Type-Options": "nosniff",
		"X-Frame-Options": "DENY",
		"Referrer-Policy": "strict-origin-when-cross-origin",
		"Content-Security-Policy": CONTENT_SECURITY_POLICY,
	}

	if production:
		headers["Strict-Transport-Security"] = "max-age=63072000"

	return headers