"""
Shared FastAPI dependencies.
"""

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer

import server.auth as auth
import server.db as db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/external/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/external/auth/login", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    username = auth.decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return username


async def get_current_user_flexible(
    x_api_key: str | None = Header(default=None),
    token: str | None = Depends(oauth2_scheme_optional),
) -> str:
    """Accepts either X-API-Key header or a Bearer JWT token."""
    if x_api_key:
        username = await db.get_username_by_api_key(auth.hash_api_key(x_api_key))
        if username:
            return username
    if token:
        username = auth.decode_token(token)
        if username:
            return username
    raise HTTPException(status_code=401, detail="authentication required")
