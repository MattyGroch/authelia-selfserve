import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import RegistrationRequest, RequestStatus
from app.services.email import send_denial_email, send_welcome_email
from app.services.yaml_manager import add_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

_session_serializer = URLSafeTimedSerializer(settings.secret_key)
_SESSION_SALT = "admin-session"
_SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours


def _create_session_cookie() -> str:
    return _session_serializer.dumps("admin", salt=_SESSION_SALT)


def _verify_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        _session_serializer.loads(token, salt=_SESSION_SALT, max_age=_SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": None, "year": datetime.now(timezone.utc).year},
    )


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if password != settings.admin_password:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Invalid password.", "year": datetime.now(timezone.utc).year},
        )
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        "admin_session",
        _create_session_cookie(),
        httponly=True,
        samesite="strict",
        max_age=_SESSION_MAX_AGE,
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie("admin_session")
    return response


@router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
    flash: str | None = None,
):
    if not _verify_session(admin_session):
        return RedirectResponse("/admin/login", status_code=303)

    result = await db.execute(
        select(RegistrationRequest).order_by(
            RegistrationRequest.status.asc(),
            RegistrationRequest.created_at.desc(),
        )
    )
    all_requests = result.scalars().all()
    pending_count = sum(1 for r in all_requests if r.status == RequestStatus.PENDING)

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "requests": all_requests,
            "pending_count": pending_count,
            "flash": flash,
            "year": datetime.now(timezone.utc).year,
        },
    )


async def _resolve_request(
    request_id: int, action: str, db: AsyncSession
) -> RegistrationRequest | None:
    result = await db.execute(
        select(RegistrationRequest).where(RegistrationRequest.id == request_id)
    )
    reg = result.scalar_one_or_none()
    if not reg or reg.status != RequestStatus.PENDING:
        return None

    if action == "approve":
        await add_user(
            username=reg.username,
            display_name=reg.display_name,
            email=reg.email,
            password_hash=reg.password_hash,
        )
        reg.status = RequestStatus.APPROVED
        reg.resolved_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            await send_welcome_email(reg.email, reg.username, reg.display_name)
        except Exception:
            logger.warning("Failed to send welcome email to %s", reg.email)

    elif action == "deny":
        reg.status = RequestStatus.DENIED
        reg.resolved_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            await send_denial_email(reg.email, reg.display_name)
        except Exception:
            logger.warning("Failed to send denial email to %s", reg.email)

    return reg


@router.post("/approve/{request_id}")
async def approve_request(
    request: Request,
    request_id: int,
    admin_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not _verify_session(admin_session):
        return RedirectResponse("/admin/login", status_code=303)

    reg = await _resolve_request(request_id, "approve", db)
    flash = f"User '{reg.username}' approved." if reg else "Request not found or already resolved."
    return await dashboard(request, admin_session, db, flash=flash)


@router.post("/deny/{request_id}")
async def deny_request(
    request: Request,
    request_id: int,
    admin_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not _verify_session(admin_session):
        return RedirectResponse("/admin/login", status_code=303)

    reg = await _resolve_request(request_id, "deny", db)
    flash = f"User '{reg.username}' denied." if reg else "Request not found or already resolved."
    return await dashboard(request, admin_session, db, flash=flash)
