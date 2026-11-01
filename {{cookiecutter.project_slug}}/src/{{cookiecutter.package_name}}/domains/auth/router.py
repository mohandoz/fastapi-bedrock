"""Authentication routes: register, login, refresh, logout and account lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

{% if cookiecutter.use_rate_limiting == "yes" -%}
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
{%- else -%}
from fastapi import APIRouter, BackgroundTasks, Depends, status
{%- endif %}
from fastapi.security import OAuth2PasswordRequestForm

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import SessionDep
from {{ cookiecutter.package_name }}.core.exceptions import ForbiddenError
{%- if cookiecutter.use_rate_limiting == "yes" %}
from {{ cookiecutter.package_name }}.core.rate_limit import limiter
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
from {{ cookiecutter.package_name }}.core.redis import RedisClient
{%- endif %}
from {{ cookiecutter.package_name }}.domains.auth.dependencies import CurrentUser
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository
from {{ cookiecutter.package_name }}.domains.auth.schemas import (
    EmailVerificationRequest,
    EmailVerificationResendRequest,
    Message,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    Token,
    UserCreate,
    UserExport,
    UserRead,
)
from {{ cookiecutter.package_name }}.domains.auth.service import AuthService
from {{ cookiecutter.package_name }}.domains.auth.token_store import RefreshTokenStore


{% if cookiecutter.use_redis == "yes" -%}
def get_auth_service(session: SessionDep, redis_client: RedisClient) -> AuthService:
    return AuthService(UserRepository(session), RefreshTokenStore(redis_client))
{%- else -%}
def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(UserRepository(session), RefreshTokenStore(session))
{%- endif %}


ServiceDep = Annotated[AuthService, Depends(get_auth_service)]

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
{%- if cookiecutter.use_rate_limiting == "yes" %}
# Stricter than the global default: registration is unauthenticated and abusable.
@limiter.limit("5/minute")
async def register(
    request: Request,
    data: UserCreate,
    background_tasks: BackgroundTasks,
    service: ServiceDep,
) -> User:
{%- else %}
async def register(
    data: UserCreate, background_tasks: BackgroundTasks, service: ServiceDep
) -> User:
{%- endif %}
    if not settings.open_registration:
        raise ForbiddenError("Registration is disabled")
    user = await service.register(data)
    if settings.require_email_verification:
        message = service.prepare_verification_email(user)
        # Function-scoped DB dependencies commit before Starlette runs response
        # background tasks, so a verification link is never sent for a user row
        # that later fails to commit.
        background_tasks.add_task(service.deliver_verification_email, message)
    return user


@router.post("/login", response_model=Token)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("10/minute")
async def login(
    request: Request,
{%- else %}
async def login(
{%- endif %}
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: ServiceDep,
) -> Token:
    user = await service.authenticate(form_data.username, form_data.password)
    return await service.issue_tokens(user)


@router.post("/refresh", response_model=Token)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("30/minute")
async def refresh(request: Request, data: RefreshRequest, service: ServiceDep) -> Token:
{%- else %}
async def refresh(data: RefreshRequest, service: ServiceDep) -> Token:
{%- endif %}
    """Rotate the refresh token. Reusing an already-rotated token revokes its family."""
    return await service.refresh_tokens(data.refresh_token)


@router.post("/logout", response_model=Message)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("30/minute")
async def logout(request: Request, data: RefreshRequest, service: ServiceDep) -> Message:
{%- else %}
async def logout(data: RefreshRequest, service: ServiceDep) -> Message:
{%- endif %}
    """Revoke the refresh-token family; access tokens ride out their short expiry."""
    await service.logout(data.refresh_token)
    return Message(detail="Logged out")


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.get("/me/export", response_model=UserExport)
async def export_me(current_user: CurrentUser) -> UserExport:
    """Machine-readable copy of the account's stored data (GDPR data portability)."""
    return UserExport(user=UserRead.model_validate(current_user), exported_at=datetime.now(UTC))


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(current_user: CurrentUser, service: ServiceDep) -> None:
    """Permanently erase the account (GDPR right to erasure — hard delete)."""
    await service.delete_account(current_user)


@router.post("/password", response_model=Message)
async def change_password(
    data: PasswordChange, current_user: CurrentUser, service: ServiceDep
) -> Message:
    """Change the password; the current password must be supplied as proof."""
    await service.change_password(current_user, data.current_password, data.new_password)
    return Message(detail="Password updated")


@router.post("/forgot-password", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
{%- if cookiecutter.use_rate_limiting == "yes" %}
# Stricter than the global default: each request can trigger an outbound email.
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    service: ServiceDep,
) -> Message:
{%- else %}
async def forgot_password(
    data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    service: ServiceDep,
) -> Message:
{%- endif %}
    message = await service.prepare_password_reset(data.email)
    if message is not None:
        background_tasks.add_task(service.deliver_password_reset, message)
    # Identical response whether or not the account exists (no enumeration).
    return Message(detail="If the account exists, a password reset email has been sent")


@router.post("/reset-password", response_model=Message)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    data: PasswordResetConfirm,
    service: ServiceDep,
) -> Message:
{%- else %}
async def reset_password(data: PasswordResetConfirm, service: ServiceDep) -> Message:
{%- endif %}
    await service.reset_password(data.token, data.new_password)
    return Message(detail="Password updated")


@router.post("/verify-email", response_model=Message)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    data: EmailVerificationRequest,
    service: ServiceDep,
) -> Message:
{%- else %}
async def verify_email(data: EmailVerificationRequest, service: ServiceDep) -> Message:
{%- endif %}
    await service.verify_email(data.token)
    return Message(detail="Email address verified")


@router.post(
    "/resend-verification",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("5/minute")
async def resend_verification(
    request: Request,
    data: EmailVerificationResendRequest,
    background_tasks: BackgroundTasks,
    service: ServiceDep,
) -> Message:
{%- else %}
async def resend_verification(
    data: EmailVerificationResendRequest,
    background_tasks: BackgroundTasks,
    service: ServiceDep,
) -> Message:
{%- endif %}
    message = await service.prepare_verification_resend(data.email)
    if message is not None:
        background_tasks.add_task(service.deliver_verification_email, message)
    return Message(detail="If verification is required, a new email has been sent")
