import uuid
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_session_token
from app.models.user import AuthSession, User
from app.services.auth.permissions import Permission, has_permission


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"error_code": code, "message": message})


def _aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes even for timezone=True columns.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get_current_user(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> User:
    """The signed-in user, from the httpOnly session cookie. Every API route
    (except health and the sign-up/login endpoints) depends on this."""
    if not session_token:
        raise _unauthorized("NOT_AUTHENTICATED", "Please sign in to continue.")
    session = db.query(AuthSession).filter(AuthSession.token_hash == hash_session_token(session_token)).first()
    if session is None or _aware(session.expires_at) <= datetime.now(timezone.utc):
        raise _unauthorized("SESSION_EXPIRED", "Your session has expired. Please sign in again.")
    return session.user


def get_current_tenant_id(user: User = Depends(get_current_user)) -> uuid.UUID:
    """The signed-in user's tenant. Every workbook/record query filters on
    this, so one user can never read or change another user's data."""
    return user.tenant_id


def require_permission(permission: Permission):
    """Dependency factory: 403 unless the user's role grants ``permission``."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=403,
                detail={"error_code": "FORBIDDEN", "message": "You don't have permission to do that."},
            )
        return user

    return checker
