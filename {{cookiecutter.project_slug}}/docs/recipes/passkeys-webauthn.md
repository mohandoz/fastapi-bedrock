# Recipe: passkeys (WebAuthn) with py_webauthn

Adds passkey sign-in alongside the existing password flow using
[py_webauthn](https://github.com/duo-labs/py_webauthn) (PyPI package
`webauthn`, Duo/Cisco-maintained — the consensus server-side implementation).
As with the social-login recipe, the credential proves the user's identity and
this service still mints its **own** access/refresh pair via
`AuthService.issue_tokens`, so everything downstream (dependencies, refresh
rotation, logout) is unchanged.

WebAuthn is a four-step dance, two round trips per operation:

1. **Registration**: server issues options + challenge → browser creates a
   credential (`navigator.credentials.create`) → server verifies and stores
   the public key.
2. **Authentication**: server issues options + challenge → browser signs it
   (`navigator.credentials.get`) → server verifies the signature against the
   stored public key and issues tokens.

## 1. Install

```bash
uv add webauthn
```

## 2. Settings

Add to the *Security* block in `src/{{ cookiecutter.package_name }}/core/config.py`:

```python
    # --- WebAuthn (passkeys) ---
    # The Relying Party ID is your registrable domain — no scheme, no port.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = settings.project_name
    # The exact web origin the browser reports, scheme and port included.
    webauthn_origin: str = "http://localhost:3000"
```

In production these become e.g. `WEBAUTHN_RP_ID=example.com` and
`WEBAUTHN_ORIGIN=https://app.example.com`. Getting either wrong is the
number-one WebAuthn failure mode — verification rejects mismatches by design.

## 3. Credential model

Passkeys are *additional* credentials, not a replacement for the user row: one
user can hold several (laptop, phone, security key). Add to
`src/{{ cookiecutter.package_name }}/domains/auth/models.py`:

```python
import uuid

from {{ cookiecutter.package_name }}.core.models import TimestampMixin


class WebAuthnCredential(TimestampMixin, SQLModel, table=True):
    """One registered passkey. A user may have many."""

    __tablename__ = "webauthn_credentials"

    # base64url-encoded credential ID chosen by the authenticator.
    credential_id: str = Field(primary_key=True, max_length=1024)
    user_id: uuid.UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    # COSE public key, stored raw; py_webauthn consumes/produces bytes.
    public_key: bytes
    # Signature counter for clone detection (0 for most platform passkeys).
    sign_count: int = Field(default=0)
    # Comma-separated hints ("internal,hybrid") — helps browsers pick a path.
    transports: str | None = Field(default=None, max_length=255)
    # User-facing label ("MacBook Touch ID") for a "manage passkeys" page.
    nickname: str | None = Field(default=None, max_length=255)
```

`ON DELETE CASCADE` ties credentials to their user, so GDPR account erasure
removes them in the same statement — mirroring the `refresh_tokens` table.
Then generate a migration: `make revision m="add webauthn credentials"`.

## 4. Challenge storage

Both flows issue a random challenge that must be held server-side between the
options request and the verify request (it is what makes a signature fresh).
Store it keyed by user (registration) or by a random session handle
(authentication), with a short TTL — five minutes is plenty.
{% if cookiecutter.use_redis == "yes" %}The shipped cache helper is exactly
this shape: `await cache.set(f"webauthn:{key}", challenge, ttl=300)` in the
options endpoint, `await cache.get(...)` + delete in the verify endpoint
(`core/cache.py`, injected with `CacheDep`).
{%- else %}Without Redis, a small `webauthn_challenges` table (key, challenge,
expires_at) works — sweep expired rows opportunistically, as
`domains/auth/token_store.py` does for refresh tokens.
{%- endif %}

## 5. Flow sketch

`src/{{ cookiecutter.package_name }}/domains/auth/webauthn.py` — the four
routes, with the py_webauthn calls spelled out and storage abbreviated:

```python
"""Passkey (WebAuthn) registration and login."""

from __future__ import annotations

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from {{ cookiecutter.package_name }}.core.config import settings

router = APIRouter(prefix="/auth/webauthn", tags=["auth"])


@router.post("/register/options")
async def registration_options(current_user: CurrentUser) -> Response:
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=current_user.id.bytes,
        user_name=current_user.email,
        # exclude_credentials: pass the user's existing credential IDs so the
        # browser refuses to register the same authenticator twice.
    )
    # store options.challenge for this user (see "Challenge storage")
    return Response(content=options_to_json(options), media_type="application/json")


@router.post("/register/verify", status_code=status.HTTP_201_CREATED)
async def registration_verify(
    body: dict,  # the JSON from navigator.credentials.create()
    current_user: CurrentUser,
    session: SessionDep,
) -> Message:
    verified = verify_registration_response(
        credential=body,
        expected_challenge=stored_challenge,  # from "Challenge storage"
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
    )
    session.add(
        WebAuthnCredential(
            credential_id=bytes_to_base64url(verified.credential_id),
            user_id=current_user.id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
        )
    )
    await session.commit()
    return Message(detail="Passkey registered")


@router.post("/login/options")
async def authentication_options() -> Response:
    # Usernameless: allow_credentials empty lets the browser offer any
    # discoverable passkey for this rp_id.
    options = generate_authentication_options(rp_id=settings.webauthn_rp_id)
    # store options.challenge under a random handle returned to the client
    return Response(content=options_to_json(options), media_type="application/json")


@router.post("/login/verify", response_model=Token)
async def authentication_verify(
    body: dict,  # the JSON from navigator.credentials.get()
    service: ServiceDep,
    session: SessionDep,
) -> Token:
    credential = await session.get(WebAuthnCredential, body["id"])
    if credential is None:
        raise UnauthorizedError("Unknown passkey")
    verified = verify_authentication_response(
        credential=body,
        expected_challenge=stored_challenge,  # single-use: delete after load
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
        credential_public_key=credential.public_key,
        credential_current_sign_count=credential.sign_count,
    )
    credential.sign_count = verified.new_sign_count
    await session.commit()
    user = await UserRepository(session).get(credential.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Inactive user")
    return await service.issue_tokens(user)
```

Register it in `api/router.py` like any other router. Verification failures
raise `webauthn.helpers.exceptions.InvalidRegistrationResponse` /
`InvalidAuthenticationResponse` — catch them and re-raise the project's
`UnauthorizedError` so clients get the standard RFC 9457 problem document.

## 6. Frontend

The browser side is `navigator.credentials.create()` / `.get()` fed with the
options JSON (fields arrive base64url-encoded and need decoding to
`ArrayBuffer`s). Use
[@simplewebauthn/browser](https://simplewebauthn.dev/docs/packages/browser)
rather than hand-rolling that plumbing — `startRegistration(options)` and
`startAuthentication(options)` pair exactly with the four endpoints above.

## Notes

- **Keep the password + reset flow.** Passkeys are an *addition*; account
  recovery still needs an independent path. Offer "add a passkey" from the
  authenticated settings page (which is why `register/options` requires
  `CurrentUser`).
- **`sign_count`** — a decreasing counter suggests a cloned authenticator;
  py_webauthn raises on regression. Synced platform passkeys (iCloud
  Keychain, Google Password Manager) legitimately report 0 forever.
- **User verification.** `generate_authentication_options` defaults to
  requiring user verification (Face ID / PIN); relax with
  `user_verification=UserVerificationRequirement.PREFERRED` if you support
  bare security keys.
- **rp_id vs origin.** `rp_id` is the registrable domain (`example.com`
  covers `app.example.com`); `origin` must match the browser's origin
  exactly, scheme and port included. `localhost` is a valid rp_id for
  development; any other host needs HTTPS.
- **Further reading:** [passkeys.dev](https://passkeys.dev) for platform
  behaviour, the [py_webauthn docs](https://github.com/duo-labs/py_webauthn)
  for every option not shown here.
