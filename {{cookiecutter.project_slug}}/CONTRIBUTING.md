# Contributing

Thanks for contributing to {{ cookiecutter.project_name }}!

## Getting set up

```bash
make install   # installs dependencies and the pre-commit hooks
```

## Before you open a pull request

Run the full check suite and make sure it passes:

```bash
make check     # ruff lint + format check, mypy, and the test suite
```

- Format and auto-fix with `make format`.
- Add tests for any behaviour you change; keep coverage healthy.
- If you change models, generate a migration: `make revision m="..."`.
- Record user-facing changes under **[Unreleased]** in `CHANGELOG.md`.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):
`<type>(<scope>): <imperative summary>`

- **Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`, `chore`.
- **Scope:** the domain or area touched, e.g. `{{ cookiecutter.first_entity }}`, `core`, `api`.
- Breaking change: append `!` after the type/scope and explain it in the body.

```text
feat({{ cookiecutter.first_entity }}): add archived filter to the list endpoint
fix(core): roll back the session when commit fails
```

## Conventions

- Keep business logic in `services`, data access in `repositories`, and HTTP
  concerns in `router` modules.
- Each new domain lives under `src/{{ cookiecutter.package_name }}/domains/<name>/`
  and mirrors the existing structure (models, schemas, repository, service,
  router) — scaffold one with `make new-domain name=<name>` (or
  `uv run python scripts/new_domain.py <name>`).
- Public commits should pass pre-commit; it runs automatically on `git commit`.

## Staying current with the template

This project was generated from the **fastapi-bedrock** Cookiecutter template.
If it was created with [cruft](https://cruft.github.io/cruft/)
(`uvx cruft create ...`), pull in template improvements later with:

```bash
uvx cruft check    # is the project behind the template?
uvx cruft update   # apply upstream template changes as a local diff
```

Review the diff, resolve any `.rej` conflicts, run `make check`, and commit it
like any other change. Projects generated with plain `cookiecutter` have no
`.cruft.json` and cannot use `cruft update`.
