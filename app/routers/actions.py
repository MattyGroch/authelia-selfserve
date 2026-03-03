import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegistrationRequest, RequestStatus
from app.services.email import send_denial_email, send_welcome_email
from app.services.tokens import verify_action_token
from app.services.yaml_manager import add_user

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _result(request: Request, *, success: bool, title: str, message: str):
    return templates.TemplateResponse(
        "action_result.html",
        {
            "request": request,
            "success": success,
            "title": title,
            "message": message,
            "year": datetime.now(timezone.utc).year,
        },
    )


@router.get("/action/{token}", response_class=HTMLResponse)
async def handle_action(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    payload = verify_action_token(token)
    if payload is None:
        return _result(
            request,
            success=False,
            title="Invalid or Expired Link",
            message="This action link is invalid or has expired. Please use the admin dashboard instead.",
        )

    request_id = payload["id"]
    action = payload["action"]

    result = await db.execute(
        select(RegistrationRequest).where(RegistrationRequest.id == request_id)
    )
    reg = result.scalar_one_or_none()

    if not reg:
        return _result(
            request,
            success=False,
            title="Request Not Found",
            message="The registration request was not found.",
        )

    if reg.status != RequestStatus.PENDING:
        return _result(
            request,
            success=False,
            title="Already Resolved",
            message=f"This request has already been {reg.status.value}.",
        )

    if action == "approve":
        try:
            await add_user(
                username=reg.username,
                display_name=reg.display_name,
                email=reg.email,
                password_hash=reg.password_hash,
            )
        except ValueError as exc:
            return _result(
                request,
                success=False,
                title="Approval Failed",
                message=str(exc),
            )

        reg.status = RequestStatus.APPROVED
        reg.resolved_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            await send_welcome_email(reg.email, reg.username, reg.display_name)
        except Exception:
            logger.warning("Failed to send welcome email to %s", reg.email)

        return _result(
            request,
            success=True,
            title="User Approved",
            message=f"'{reg.username}' has been added to Authelia and notified by email.",
        )

    elif action == "deny":
        reg.status = RequestStatus.DENIED
        reg.resolved_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            await send_denial_email(reg.email, reg.display_name)
        except Exception:
            logger.warning("Failed to send denial email to %s", reg.email)

        return _result(
            request,
            success=True,
            title="User Denied",
            message=f"The registration request for '{reg.username}' has been denied.",
        )

    return _result(
        request,
        success=False,
        title="Unknown Action",
        message="The action in this link is not recognized.",
    )
