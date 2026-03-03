from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key)
_SALT = "registration-action"


def create_action_token(request_id: int, action: str) -> str:
    """Create a signed token encoding the request id and action (approve/deny)."""
    return _serializer.dumps({"id": request_id, "action": action}, salt=_SALT)


def verify_action_token(token: str) -> dict | None:
    """Verify and decode a token. Returns payload dict or None if invalid/expired."""
    max_age = settings.token_expiry_hours * 3600
    try:
        payload = _serializer.loads(token, salt=_SALT, max_age=max_age)
        return payload
    except (BadSignature, SignatureExpired):
        return None
