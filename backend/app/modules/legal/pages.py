# backend/app/modules/legal/pages.py

"""HTML-маршруты юридических документов с сохранением прежних адресов."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi_csrf_protect import CsrfProtect
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse
from backend.app.core.logging import get_logger
from backend.app.modules.auth.dependencies import get_optional_user
from backend.app.modules.legal.service import LegalDocumentUnavailable, load_legal_document
from backend.app.modules.users.models.user import User
from backend.app.web.rendering import render_page


log = get_logger(__name__)
router = APIRouter(tags=["legal-pages"])

OptionalUser = Annotated[User | None, Depends(get_optional_user)]
PageCsrf = Annotated[CsrfProtect, Depends()]

async def _render_document(request: Request, user: User | None, csrf_protect: CsrfProtect, document_key: str) -> HTMLResponse:
	try:
		document = await run_in_threadpool(load_legal_document, document_key)
	except LegalDocumentUnavailable:
		log.exception("Не удалось загрузить юридический документ: %s", document_key)
		raise HTTPException(
			status_code=503, detail="Документ временно недоступен.", headers={"Cache-Control": "no-store"},
		) from None

	context = {"user": user, "legal_title": document.title, "legal_content": document.content}
	return render_page(request, "legal/document.html", context, csrf_protect)

@router.get("/cookie-policy", response_class=HTMLResponse, name="cookie_policy_page_get")
async def get_cookie_policy_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return await _render_document(request, user, csrf_protect, "cookie-policy")

@router.get("/privacy-policy", response_class=HTMLResponse, name="privacy_policy_page_get")
async def get_privacy_policy_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return await _render_document(request, user, csrf_protect, "privacy-policy")

@router.get("/terms", response_class=HTMLResponse, name="terms_page_get")
async def get_terms_page(request: Request, user: OptionalUser, csrf_protect: PageCsrf) -> HTMLResponse:
	return await _render_document(request, user, csrf_protect, "terms")