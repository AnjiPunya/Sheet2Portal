"""Sign up, log in, log out, and "who am I".

Sessions live in an httpOnly, SameSite=Lax cookie (JavaScript can't read
it, and browsers don't send it on cross-site POSTs). Passwords are hashed
with scrypt; only a hash of each session token is stored.
"""

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_password, hash_session_token, new_session_token, verify_password
from app.models.tenant import Tenant
from app.models.user import AuthSession, User
from app.schemas.auth import LoginIn, SignUpIn, UserOut
from app.services.auth.permissions import permissions_for

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Failed-login throttle, per email, in memory (per process). Enough to stop
# naive password guessing; a shared store would be needed across instances.
_MAX_FAILURES = 10
_FAILURE_WINDOW_SECONDS = 15 * 60
_failures: dict[str, deque[float]] = defaultdict(deque)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_code": code, "message": message})


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        permissions=sorted(permissions_for(user.role)),
    )


def _start_session(db: Session, user: User, response: Response) -> None:
    token = new_session_token()
    ttl = timedelta(hours=settings.session_ttl_hours)
    db.add(AuthSession(user_id=user.id, token_hash=hash_session_token(token), expires_at=datetime.now(timezone.utc) + ttl))
    db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def _recent_failures(email: str) -> deque[float]:
    attempts = _failures[email]
    cutoff = time.monotonic() - _FAILURE_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return attempts


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(payload: SignUpIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    if db.query(User).filter(User.email == payload.email).first():
        raise _error(409, "EMAIL_TAKEN", "An account with this email already exists. Try signing in.")
    # Each user gets their own tenant, so all existing tenant filtering
    # isolates their workbooks from everyone else's.
    tenant = Tenant(name=payload.email)
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        display_name=payload.display_name.strip() or payload.email.split("@")[0],
        password_hash=hash_password(payload.password),
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _start_session(db, user, response)
    return _user_out(user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    attempts = _recent_failures(payload.email)
    if len(attempts) >= _MAX_FAILURES:
        raise _error(429, "TOO_MANY_ATTEMPTS", "Too many failed sign-in attempts. Please wait a few minutes and try again.")
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        attempts.append(time.monotonic())
        # Same message either way, so the endpoint doesn't reveal which emails exist.
        raise _error(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    attempts.clear()
    _start_session(db, user, response)
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> Response:
    if session_token:
        db.query(AuthSession).filter(AuthSession.token_hash == hash_session_token(session_token)).delete()
        db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)
