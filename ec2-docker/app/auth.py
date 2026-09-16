import os
import time

import bcrypt
import jwt
from fastapi import Header, HTTPException

# Change this in production - a long random string. Falls back to a default
# only for convenience in local/dev use; set JWT_SECRET in your environment
# for anything you actually care about.
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-change-me-please")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return claims["sub"]
