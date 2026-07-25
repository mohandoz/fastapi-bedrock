# Recipes

Every generated project ships a `docs/recipes/` directory: integration guides
written **against the generated codebase** — they name the real modules,
settings blocks and service methods, so the diff between the recipe and your
project is minimal. They are rendered with your project's package name during
generation.

The sources live in the template at
[`{{cookiecutter.project_slug}}/docs/recipes/`](https://github.com/mohandoz/fastapi-bedrock/tree/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/recipes)
(the links below point there; in your generated project the same files are in
`docs/recipes/` with all placeholders filled in).

## Shipped in every project

- **[Background work: which tool?](https://github.com/mohandoz/fastapi-bedrock/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/recipes/background-jobs.md)**
  — `BackgroundTasks` vs the transactional outbox vs Temporal, with a decision
  table and one worked example of each. Read it before adding any async work.
- **[Admin back-office with SQLAdmin](https://github.com/mohandoz/fastapi-bedrock/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/recipes/admin-sqladmin.md)**
  — a model-driven admin UI over the existing SQLModel tables.
- **[Feature flags with OpenFeature](https://github.com/mohandoz/fastapi-bedrock/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/recipes/feature-flags-openfeature.md)**
  — vendor-neutral flag evaluation wired through the service layer.

## Shipped when `use_auth=yes`

- **[Social login (OAuth / OIDC) with Authlib](https://github.com/mohandoz/fastapi-bedrock/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/recipes/oauth-social-login.md)**
  — "Sign in with Google" alongside the password flow; the service still mints
  its own JWT pair, so everything downstream is unchanged.
- **[Cloudflare Turnstile verification](https://github.com/mohandoz/fastapi-bedrock/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/recipes/turnstile-verification.md)**
  — a ~40-line dependency that shields unauthenticated endpoints (register,
  forgot-password) from bot abuse; no-ops until a secret key is configured,
  so it costs nothing in development.
- **[Passkeys / WebAuthn readiness](https://github.com/mohandoz/fastapi-bedrock/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/recipes/passkeys-webauthn.md)**
  — a credential model alongside the existing `users` table and the
  registration/authentication flows with `py_webauthn`, ending in the same
  token issuance the password flow uses.

## Writing your own

Recipes are deliberately *documentation, not flags*: they keep the template's
surface small while showing the exact upgrade path. If you build an
integration you think belongs here,
[contributions are welcome](https://github.com/mohandoz/fastapi-bedrock/blob/main/CONTRIBUTING.md)
— a good recipe names real files in the generated project, provides complete
copy-pasteable code, and explains the trade-offs at the end.
