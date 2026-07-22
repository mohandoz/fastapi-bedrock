"""Authentication dependencies: resolve the current user from a bearer token."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import get_session
from {{ cookiecutter.package_name }}.core.exceptions import ForbiddenError, UnauthorizedError
from {{ cookiecutter.package_name }}.core.security import decode_token
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Could not validate credentials") from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")
    subject = payload.get("sub")
    if subject is None:
        raise UnauthorizedError("Could not validate credentials")
    try:
        user_id = UUID(subject)
    except ValueError as exc:
        raise UnauthorizedError("Could not validate credentials") from exc
    user = await UserRepository(session).get(user_id)
    if user is None:
        raise UnauthorizedError("User not found")
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise ForbiddenError("Inactive user")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_active_user)]
