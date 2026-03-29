import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

import server.auth as auth
import server.db as db

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

BETA_KEY = os.environ.get("BETA_KEY", "")


class AuthRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(AuthRequest):
    beta_key: str


@router.post("/auth/register")
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest):
    if not BETA_KEY or body.beta_key != BETA_KEY:
        raise HTTPException(status_code=403, detail="invalid beta key")
    pw_hash = auth.hash_password(body.password)
    created = await db.create_user(body.username, pw_hash)
    if not created:
        raise HTTPException(status_code=400, detail="username already taken")
    logger.info("%s registered", body.username, extra={"tags": {"username": body.username, "action": "registered"}})
    token = auth.create_token(body.username)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, body: AuthRequest):
    pw_hash = await db.get_password_hash(body.username)
    if not pw_hash or not auth.verify_password(body.password, pw_hash):
        logger.warning("%s failed login", body.username, extra={"tags": {"username": body.username, "action": "login_failed"}})
        raise HTTPException(status_code=401, detail="invalid credentials")
    logger.info("%s logged in", body.username, extra={"tags": {"username": body.username, "action": "login"}})
    token = auth.create_token(body.username)
    return {"access_token": token, "token_type": "bearer"}
