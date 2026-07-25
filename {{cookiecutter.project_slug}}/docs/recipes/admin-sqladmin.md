# Recipe: admin back-office with SQLAdmin

{%- set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') %}

[SQLAdmin](https://aminalaee.dev/sqladmin/) generates a CRUD UI straight from
the SQLModel tables and works with the async engine this template already
builds (`core/database.py`).

## 1. Install

```bash
uv add sqladmin
```

## 2. The admin module

`src/{{ cookiecutter.package_name }}/admin.py`:

```python
"""SQLAdmin back-office, mounted at /admin."""

from __future__ import annotations

from fastapi import FastAPI
from sqladmin import Admin, ModelView

from {{ cookiecutter.package_name }}.core.database import engine
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth.models import User
{%- endif %}


class {{ entity_class }}Admin(ModelView, model={{ entity_class }}):
    column_list = [{{ entity_class }}.id, {{ entity_class }}.created_at]
    column_searchable_list = [{{ entity_class }}.id]
    page_size = 50
{%- if cookiecutter.use_auth == "yes" %}


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.email, User.is_active, User.is_superuser]
    column_details_exclude_list = [User.hashed_password]
    form_excluded_columns = [User.hashed_password]
    can_create = False  # accounts come from /auth/register, not the admin
{%- endif %}


def mount_admin(app: FastAPI) -> None:
    admin = Admin(app, engine, authentication_backend=AdminAuth())
    admin.add_view({{ entity_class }}Admin)
{%- if cookiecutter.use_auth == "yes" %}
    admin.add_view(UserAdmin)
{%- endif %}
```

## 3. Authentication

SQLAdmin guards `/admin` with an `AuthenticationBackend` (it adds its own
session middleware using the secret you pass).
{% if cookiecutter.use_auth == "yes" %}
Reuse the template's user store — only active **superusers** get in (create one
via `FIRST_SUPERUSER_EMAIL`/`FIRST_SUPERUSER_PASSWORD`). Add to `admin.py`:

```python
from fastapi.concurrency import run_in_threadpool
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import async_session_factory
from {{ cookiecutter.package_name }}.core.security import verify_password
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository


class AdminAuth(AuthenticationBackend):
    def __init__(self) -> None:
        super().__init__(secret_key=settings.secret_key)

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = str(form.get("username", "")).lower()
        password = str(form.get("password", ""))
        async with async_session_factory() as session:
            user = await UserRepository(session).get_by_email(email)
        if user is None or not user.is_active or not user.is_superuser:
            return False
        if not await run_in_threadpool(verify_password, password, user.hashed_password):
            return False
        request.session.update({"admin_user_id": str(user.id)})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return "admin_user_id" in request.session
```

For long-lived deployments, make `authenticate` re-load the user and re-check
`is_superuser` so a demoted admin loses access before the session expires.
{%- else %}
This project was generated without the auth option, so there is no user table
to check credentials against. Either re-generate with `use_auth=yes`, keep
`/admin` reachable only through a reverse proxy that enforces authentication,
or use a single shared credential from the environment:

```python
import secrets

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from {{ cookiecutter.package_name }}.core.config import settings


class AdminAuth(AuthenticationBackend):
    """Single shared credential from ADMIN_USER / ADMIN_PASSWORD settings."""

    def __init__(self) -> None:
        super().__init__(secret_key=settings.admin_password)

    async def login(self, request: Request) -> bool:
        form = await request.form()
        user_ok = secrets.compare_digest(str(form.get("username", "")), settings.admin_user)
        pass_ok = secrets.compare_digest(str(form.get("password", "")), settings.admin_password)
        if not (user_ok and pass_ok):
            return False
        request.session.update({"admin": True})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin"))
```

with `admin_user: str = "admin"` and `admin_password: str` (no default —
boot fails unless it is set) added to `core/config.py`.
{%- endif %}

## 4. Mount it

In `create_app` (`main.py`), after `include_router`:

```python
from {{ cookiecutter.package_name }}.admin import mount_admin

    mount_admin(app)
```

`make run` and open <http://localhost:8000/admin>.

## Notes

- The admin runs inside the same ASGI app, so the existing middleware
  (trusted hosts, request IDs, security headers, body-size limit) applies.
- Treat it as an internal tool: consider mounting only when
  `not settings.is_production`, or keeping `/admin` off the public ingress.
- SQLAdmin issues its own queries through the engine — repository/service
  invariants are bypassed, which is exactly why views above exclude and
  lock down sensitive columns.
