import os
import time
import requests
from jose import jwt
from fastapi import Header, HTTPException

USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]
REGION = os.environ["AWS_REGION"]

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

_jwks_cache = {"keys": None, "fetched_at": 0}


def get_jwks():
    if not _jwks_cache["keys"] or time.time() - _jwks_cache["fetched_at"] > 3600:
        resp = requests.get(JWKS_URL, timeout=10)
        resp.raise_for_status()
        _jwks_cache["keys"] = resp.json()["keys"]
        _jwks_cache["fetched_at"] = time.time()
    return _jwks_cache["keys"]


def get_current_user(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")

    try:
        header = jwt.get_unverified_header(token)
        key = next(k for k in get_jwks() if k["kid"] == header["kid"])
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=CLIENT_ID, issuer=ISSUER)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return claims["sub"]
