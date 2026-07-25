# Recipe: Cloudflare Turnstile on unauthenticated endpoints

{% if cookiecutter.use_rate_limiting == "yes" -%}
Rate limits key on client IP, which is weak against *distributed* abuse —
credential stuffing and signup floods arrive from thousands of addresses, each
comfortably under `5/minute`. [Cloudflare Turnstile](https://developers.cloudflare.com/turnstile/)
adds a CAPTCHA-less browser challenge in front of the endpoints bots care
about
{%- else -%}
Unauthenticated endpoints (registration, password reset) attract signup floods
and credential stuffing. [Cloudflare Turnstile](https://developers.cloudflare.com/turnstile/)
puts a CAPTCHA-less browser challenge in front of them
{%- endif %}: the widget issues a short-lived token that this service verifies
server-side. It is free, and the whole integration is one dependency function.

**No feature flag needed**: the dependency below no-ops while
`TURNSTILE_SECRET_KEY` is unset, so local development, tests and CI need zero
configuration and pay zero cost.

## 1. Get keys

Create a widget at <https://dash.cloudflare.com/?to=/:account/turnstile>. You
get a **sitekey** (public, used by the frontend widget) and a **secret key**
(server-side only).

## 2. Settings

Add to the *Security* block in `src/{{ cookiecutter.package_name }}/core/config.py`:

```python
    # --- Turnstile (anti-automation) ---
    # Unset = verification disabled (local development, tests).
    turnstile_secret_key: str | None = None
```

And to `.env` in deployments that enforce it:

```dotenv
TURNSTILE_SECRET_KEY=0x...
```

## 3. The dependency

`src/{{ cookiecutter.package_name }}/core/turnstile.py`:

```python
"""Cloudflare Turnstile server-side verification (anti-automation).

Attach ``Depends(verify_turnstile)`` to any unauthenticated route that bots
target. No-op while TURNSTILE_SECRET_KEY is unset.
"""

from __future__ import annotations

from typing import Annotated

import httpx
import structlog
from fastapi import Header, Request

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.exceptions import ForbiddenError

logger = structlog.get_logger()

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(
    request: Request,
    x_turnstile_token: Annotated[str | None, Header()] = None,
) -> None:
    """Reject the request unless it carries a valid Turnstile token."""
    if settings.turnstile_secret_key is None:
        return
    if not x_turnstile_token:
        raise ForbiddenError("Turnstile token required")
    payload = {
        "secret": settings.turnstile_secret_key,
        "response": x_turnstile_token,
    }
    if request.client is not None:
        payload["remoteip"] = request.client.host
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(SITEVERIFY_URL, data=payload)
    response.raise_for_status()
    outcome = response.json()
    if not outcome.get("success", False):
        logger.info(
            "turnstile.rejected",
            error_codes=outcome.get("error-codes", []),
            path=request.url.path,
        )
        raise ForbiddenError("Turnstile verification failed")
```

`httpx` already ships with `fastapi[standard]`, so there is nothing to
install.
{%- if cookiecutter.use_http_client == "yes" %} (This uses a per-call client
for simplicity; registration-volume traffic does not need pooling. If you want
retries and the circuit breaker, inject `HttpClientDep` from `core/http.py`
and call `http.post(...)` instead — but think twice about retrying siteverify:
tokens are single-use, so a retried *success* consumed the token already.)
{%- endif %}

## 4. Attach it to the abusable routes

In `src/{{ cookiecutter.package_name }}/domains/auth/router.py`, add the
dependency to the two unauthenticated endpoints that attract automation —
`register` and `forgot_password`:

```python
from {{ cookiecutter.package_name }}.core.turnstile import verify_turnstile

@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_turnstile)],
)
```

(and the same `dependencies=[Depends(verify_turnstile)]` on
`/forgot-password`).
{%- if cookiecutter.use_rate_limiting == "yes" %} Keep the existing
`@limiter.limit` decorators — rate limits and Turnstile are complementary
layers.{% endif %} Login is usually better served by per-account backoff, but
nothing stops you adding it there too.

## 5. Frontend

The widget renders in the page and produces a token your client sends as the
`X-Turnstile-Token` header:

```html
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<div class="cf-turnstile" data-sitekey="YOUR_SITEKEY" data-callback="onToken"></div>
<script>
  let turnstileToken = null;
  function onToken(token) { turnstileToken = token; }

  // on submit:
  await fetch("{{ '/api/v1' }}/auth/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Turnstile-Token": turnstileToken,
    },
    body: JSON.stringify({ email, password }),
  });
</script>
```

## 6. Tests

Cloudflare publishes fixed dummy secrets, so both paths are testable without
a real widget:

| Secret key                            | siteverify result       |
| ------------------------------------- | ----------------------- |
| `1x0000000000000000000000000000000AA` | always passes           |
| `2x0000000000000000000000000000000AA` | always fails            |
| `3x0000000000000000000000000000000AA` | "token already spent"   |

```python
async def test_register_rejected_without_turnstile_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "turnstile_secret_key", "2x0000000000000000000000000000000AA")
    response = await client.post(
        "{{ '/api/v1' }}/auth/register",
        json={"email": "bot@example.com", "password": "Str0ng-passw0rd"},  # gitleaks:allow
    )
    assert response.status_code == 403


async def test_register_unaffected_when_turnstile_disabled(client: AsyncClient) -> None:
    # turnstile_secret_key is unset in tests -> dependency is a no-op
    response = await client.post(
        "{{ '/api/v1' }}/auth/register",
        json={"email": "human@example.com", "password": "Str0ng-passw0rd"},  # gitleaks:allow
    )
    assert response.status_code == 201
```

## Notes

- **Tokens are single-use and short-lived** (about five minutes). A frontend
  that retries a failed submit must obtain a fresh token
  (`turnstile.reset()`).
- **Fail closed vs fail open.** As written, a siteverify outage raises from
  `raise_for_status()` and the request fails (500). If signup availability
  matters more than bot pressure, catch `httpx.HTTPError`, log it, and
  `return` (fail open) — a deliberate one-line policy choice.
- **Error shape.** Failures surface through the standard handlers as an
  RFC 9457 `urn:problem-type:forbidden` problem document, like every other
  `ForbiddenError`.
- **hCaptcha** has a compatible siteverify contract: swap the URL for
  `https://api.hcaptcha.com/siteverify` and the payload keys stay the same.
