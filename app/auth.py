import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-change-me")
TOKEN_TTL_SECONDS = 60 * 60 * 24
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derived).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_part, hash_part = encoded.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_part.encode())
        expected = base64.urlsafe_b64decode(hash_part.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}:{expires_at}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode().rstrip("=")
    return encoded


def decode_access_token(token: str) -> int | None:
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        user_part, expires_part, signature = decoded.split(":", 2)
        payload = f"{user_part}:{expires_part}"
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expires_part) < int(time.time()):
            return None
        return int(user_part)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user_id = decode_access_token(credentials.credentials)
    user = db.scalar(select(User).where(User.id == user_id)) if user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user
