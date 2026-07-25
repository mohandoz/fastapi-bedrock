# Security policy

This file covers the **template repository itself** (the Jinja sources, hooks
and CI). Every generated project ships its own `SECURITY.md` tailored to the
selected feature flags — report issues in *your generated service* there, not
here.

## Reporting a vulnerability

Please do not open a public issue for security problems. Instead:

- **Preferred:** open a private report at
  [github.com/mohandoz/fastapi-bedrock/security/advisories/new](https://github.com/mohandoz/fastapi-bedrock/security/advisories/new)
- **Email:** [mohannad.a@protonmail.com](mailto:mohannad.a@protonmail.com)

Include the affected template revision (commit or tag), the flag combination
used to generate the project, and reproduction steps. You should receive an
acknowledgement within a few days.

## Scope

In scope: anything the template writes into generated projects — insecure
defaults, vulnerable dependency floors, hook code (`hooks/`), CI workflows and
the vendored docs assets (`core/static/`). Out of scope: vulnerabilities in
upstream dependencies themselves (report those upstream; a floor bump here is
still welcome) and issues introduced by post-generation modifications.
