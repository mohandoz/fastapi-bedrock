# Recipe: social login (OAuth / OpenID Connect) with Authlib

Adds "Sign in with Google" alongside the existing password flow. The provider
proves the user's identity; this service still mints its **own** access/refresh
pair via `AuthService.issue_tokens`, so everything downstream (dependencies,
refresh rotation, logout) is unchanged.

Google is shown because its OpenID Connect metadata makes the wiring shortest;
any OIDC provider works the same way.

## 1. Install

```bash
uv add authlib itsdangerous
```

`itsdangerous` backs Starlette's `SessionMiddleware`, which Authlib uses to
store the `state`/`nonce` between the redirect to Google and the callback.

## 2. Settings

Add to the *Security* block in `src/{{ cookiecutter.package_name }}/core/config.py`:

```python
    # --- OAuth (social login) ---
    google_client_id: str | None = None
    google_client_secret: str | None = None
```

And to `.env` (credentials from <https://console.cloud.google.com/apis/credentials>,
with `http://localhost:8000{{ '/api/v1' }}/auth/google/callback` as an authorized
redirect URI):

```dotenv
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
```

## 3. Session middleware

In `create_app` (`main.py`), next to the other `add_middleware` calls:

```python
from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        https_only=settings.is_production,
        same_site="lax",  # the callback arrives as a cross-site redirect
    )
```

## 4. Find-or-create on the service

Add to `AuthService` (`domains/auth/service.py`):

```python
import secrets


    async def login_oauth(self, *, email: str, full_name: str | None) -> User:
        """Find or create the account behind a federated (OAuth) identity."""
        email = email.lower()
        user = await self.repository.get_by_email(email)
        if user is None:
            if not settings.open_registration:
                raise ForbiddenError("Registration is disabled")
            # No usable password: store a random throwaway hash. Password login
            # stays reachable through the reset flow if the user ever wants it.
            hashed = await run_in_threadpool(hash_password, secrets.token_urlsafe(32))
            user = User(
                email=email,
                full_name=full_name,
                is_verified=True,  # the provider verified the address
                hashed_password=hashed,
            )
            user = await self.repository.add(user)
            logger.info("auth.oauth_registered", user_id=str(user.id))
        if not user.is_active:
            raise UnauthorizedError("Inactive user")
        return user
```

## 5. The OAuth router

`src/{{ cookiecutter.package_name }}/domains/auth/oauth.py`:

```python
"""Social login: OAuth2 authorization-code flow via Authlib (Google/OIDC)."""

from __future__ import annotations

from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.exceptions import UnauthorizedError
from {{ cookiecutter.package_name }}.domains.auth.router import ServiceDep
from {{ cookiecutter.package_name }}.domains.auth.schemas import Token

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter(prefix="/auth/google", tags=["auth"])


@router.get("/login", status_code=302)
async def google_login(request: Request) -> RedirectResponse:
    redirect_uri = str(request.url_for("google_callback"))
    response: RedirectResponse = await oauth.google.authorize_redirect(request, redirect_uri)
    return response


@router.get("/callback", response_model=Token)
async def google_callback(request: Request, service: ServiceDep) -> Token:
    try:
        token: dict[str, Any] = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        raise UnauthorizedError("Google sign-in failed") from exc
    # ID-token claims — signature, nonce, audience already verified by Authlib.
    claims = token["userinfo"]
    if not claims.get("email_verified"):
        raise UnauthorizedError("Google account email is not verified")
    user = await service.login_oauth(email=claims["email"], full_name=claims.get("name"))
    return await service.issue_tokens(user)
```

Register it in `api/router.py`:

```python
from {{ cookiecutter.package_name }}.domains.auth.oauth import router as oauth_router

api_router.include_router(oauth_router)
```

Browse to `http://localhost:8000{{ '/api/v1' }}/auth/google/login` — after
consenting you get the same `Token` payload the password login returns.

## Notes

- **Account linking = email match.** An existing password account with the
  same (verified) address signs in via Google with no extra step. That is why
  the callback rejects unverified provider emails — otherwise anyone could
  claim an address at the provider and take over the matching local account.
- **SPA handoff.** Returning JSON suits API clients and `/docs`. For a browser
  app, replace the callback's return with a redirect to
  `settings.frontend_url` carrying the tokens (URL fragment, or set a cookie)
  — never put tokens in a query string that can end up in server logs.
- **Fail fast on config.** If you deploy with only one of
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` set, add a check to
  `_validate_environment_safety` in `core/config.py` mirroring the
  `FIRST_SUPERUSER_*` pair rule.
- **Other providers.** Any OIDC issuer is one more `oauth.register(...)` block
  with its own `server_metadata_url`. Providers without OIDC discovery
  (e.g. GitHub) need explicit `authorize_url`/`access_token_url` and a
  userinfo request — see the [Authlib client docs](https://docs.authlib.org/en/latest/client/starlette.html).
