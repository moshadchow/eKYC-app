"""
Security utilities — passwords, OTP, JWT, tokens.

passlib is intentionally NOT used here.
passlib 1.7.4 is incompatible with bcrypt >= 4.x: it crashes during its own
internal wrap-bug detection with "password cannot be longer than 72 bytes".
This is a known upstream issue with no fix in passlib 1.7.x.

We use the bcrypt library directly instead — simpler, actively maintained,
no version conflicts.
"""

import hashlib
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt

from app.core.config import settings


# ── Internal: SHA-256 prehash ─────────────────────────────────────────────────
# bcrypt silently truncates inputs > 72 bytes (or raises ValueError in newer
# versions). Pre-hashing with SHA-256 produces a fixed 64-byte hex digest —
# always safely under the limit. This is the same approach used by Django's
# BCryptSHA256PasswordHasher and Dropbox's password system.

def _prehash(value: str) -> bytes:
    """SHA-256 of value → 64-byte hex string → encoded to bytes for bcrypt."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()  # 64 chars
    return digest.encode("utf-8")                               # 64 bytes < 72


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Bcrypt-hash a password with SHA-256 prehash. Returns a str for DB storage."""
    hashed = bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))


# ── OTP ───────────────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP string."""
    return "".join(random.choices(string.digits, k=length))


def hash_otp(otp: str) -> str:
    """Bcrypt-hash a 6-digit OTP with SHA-256 prehash."""
    hashed = bcrypt.hashpw(_prehash(otp), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_otp(otp: str, hashed: str) -> bool:
    """Verify a plaintext OTP against its stored bcrypt hash."""
    return bcrypt.checkpw(_prehash(otp), hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    actor_type: str,
    extra: Optional[dict] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "actor_type": actor_type,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str, actor_type: str) -> str:
    return create_access_token(
        subject=subject,
        actor_type=actor_type,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        extra={"token_type": "refresh"},
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def hash_token(token: str) -> str:
    """
    SHA-256 hash of a JWT for server-side session invalidation lookup.
    Plain SHA-256 — no bcrypt needed since JWTs are already high-entropy.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Application reference ─────────────────────────────────────────────────────

def generate_application_ref() -> str:
    from datetime import date
    year = date.today().year
    random_part = "".join(random.choices(string.digits, k=6))
    return f"EKYC-{year}-{random_part}"