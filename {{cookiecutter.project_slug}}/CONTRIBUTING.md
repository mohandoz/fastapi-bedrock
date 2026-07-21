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

## Conventions

- Keep business logic in `services`, data access in `repositories`, and HTTP
  concerns in `router` modules.
- Each new domain lives under `src/{{ cookiecutter.package_name }}/domains/<name>/`
  and mirrors the existing structure (models, schemas, repository, service, router).
- Public commits should pass pre-commit; it runs automatically on `git commit`.
