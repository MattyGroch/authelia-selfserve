import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import RegistrationRequest, RequestStatus
from app.services.email import send_admin_notification
from app.services.limiter import limiter
from app.services.password import hash_password
from app.services.yaml_manager import username_exists

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")


def _make_csrf(request: Request) -> str:
    from itsdangerous import URLSafeTimedSerializer

    s = URLSafeTimedSerializer(settings.secret_key)
    return s.dumps("csrf", salt="csrf-token")


def _verify_csrf(token: str) -> bool:
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

    s = URLSafeTimedSerializer(settings.secret_key)
    try:
        s.loads(token, salt="csrf-token", max_age=3600)
        return True
    except (BadSignature, SignatureExpired):
        return False


@router.get("/", response_class=HTMLResponse)
@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "csrf_token": _make_csrf(request),
            "error": None,
            "success": None,
            "form": {},
            "year": datetime.now(timezone.utc).year,
        },
    )


@router.post("/register", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def register_submit(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    form_data = {"username": username, "display_name": display_name, "email": email}
    ctx = {
        "request": request,
        "csrf_token": _make_csrf(request),
        "form": form_data,
        "success": None,
        "error": None,
        "year": datetime.now(timezone.utc).year,
    }

    if not _verify_csrf(csrf_token):
        ctx["error"] = "Invalid or expired form session. Please try again."
        return templates.TemplateResponse("register.html", ctx)

    username = username.strip().lower()
    display_name = display_name.strip()
    email = email.strip().lower()

    if not USERNAME_RE.match(username) or len(username) < 3:
        ctx["error"] = "Username must be at least 3 characters and contain only letters, numbers, dots, dashes, or underscores."
        return templates.TemplateResponse("register.html", ctx)

    if password != password_confirm:
        ctx["error"] = "Passwords do not match."
        return templates.TemplateResponse("register.html", ctx)

    if len(password) < 8:
        ctx["error"] = "Password must be at least 8 characters."
        return templates.TemplateResponse("register.html", ctx)

    if await username_exists(username):
        ctx["error"] = "This username is already taken."
        return templates.TemplateResponse("register.html", ctx)

    existing = await db.execute(
        select(RegistrationRequest).where(
            RegistrationRequest.username == username,
            RegistrationRequest.status == RequestStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        ctx["error"] = "A registration request for this username is already pending."
        return templates.TemplateResponse("register.html", ctx)

    hashed = hash_password(password)

    reg = RegistrationRequest(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=hashed,
        status=RequestStatus.PENDING,
    )
    db.add(reg)
    await db.commit()
    await db.refresh(reg)

    try:
        await send_admin_notification(reg.id, username, display_name, email)
    except Exception:
        logger.warning("Failed to send admin notification for request %s", reg.id)

    ctx["success"] = "Your registration request has been submitted! You will receive an email once it has been reviewed."
    ctx["form"] = {}
    return templates.TemplateResponse("register.html", ctx)
