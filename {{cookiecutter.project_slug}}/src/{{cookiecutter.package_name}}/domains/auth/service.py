"""Authentication business logic: registration, login and token refresh."""

from __future__ import annotations

from uuid import UUID

import jwt
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError

from {{ cookiecutter.package_name }}.core.exceptions import ConflictError, UnauthorizedError
from {{ cookiecutter.package_name }}.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository
from {{ cookiecutter.package_name }}.domains.auth.schemas import Token, UserCreate


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def register(self, data: UserCreate) -> User:
        if await self.repository.get_by_email(data.email) is not None:
            raise ConflictError("A user with this email already exists")
        # Argon2 hashing is deliberately CPU-bound; keep it off the event loop.
        hashed = await run_in_threadpool(hash_password, data.password)
        user = User(email=data.email, full_name=data.full_name, hashed_password=hashed)
        try:
            return await self.repository.add(user)
        except IntegrityError as exc:  # lost a concurrent-registration race
            raise ConflictError("A user with this email already exists") from exc

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repository.get_by_email(email)
        if user is None:
            raise UnauthorizedError("Incorrect email or password")
        valid = await run_in_threadpool(verify_password, password, user.hashed_password)
        if not valid:
            raise UnauthorizedError("Incorrect email or password")
        if not user.is_active:
            raise UnauthorizedError("Inactive user")
        return user

    def issue_tokens(self, user: User) -> Token:
        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def refresh_tokens(self, refresh_token: str) -> Token:
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        subject = payload.get("sub")
        if subject is None:
            raise UnauthorizedError("Invalid refresh token")
        try:
            user_id = UUID(subject)
        except ValueError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        user = await self.repository.get(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("User is no longer valid")
        return self.issue_tokens(user)
