"""Authentication routes: register, login, refresh and current-user."""

from __future__ import annotations

from typing import Annotated

{% if cookiecutter.use_rate_limiting == "yes" -%}
from fastapi import APIRouter, Depends, Request, status
{%- else -%}
from fastapi import APIRouter, Depends, status
{%- endif %}
from fastapi.security import OAuth2PasswordRequestForm

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import SessionDep
from {{ cookiecutter.package_name }}.core.exceptions import ForbiddenError
{%- if cookiecutter.use_rate_limiting == "yes" %}
from {{ cookiecutter.package_name }}.core.rate_limit import limiter
{%- endif %}
from {{ cookiecutter.package_name }}.domains.auth.dependencies import CurrentUser
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository
from {{ cookiecutter.package_name }}.domains.auth.schemas import (
    RefreshRequest,
    Token,
    UserCreate,
    UserRead,
)
from {{ cookiecutter.package_name }}.domains.auth.service import AuthService


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(UserRepository(session))


ServiceDep = Annotated[AuthService, Depends(get_auth_service)]

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
{%- if cookiecutter.use_rate_limiting == "yes" %}
# Stricter than the global default: registration is unauthenticated and abusable.
@limiter.limit("5/minute")
async def register(request: Request, data: UserCreate, service: ServiceDep) -> User:
{%- else %}
async def register(data: UserCreate, service: ServiceDep) -> User:
{%- endif %}
    if not settings.open_registration:
        raise ForbiddenError("Registration is disabled")
    return await service.register(data)


@router.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: ServiceDep,
) -> Token:
    user = await service.authenticate(form_data.username, form_data.password)
    return service.issue_tokens(user)


@router.post("/refresh", response_model=Token)
async def refresh(data: RefreshRequest, service: ServiceDep) -> Token:
    return await service.refresh_tokens(data.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user
