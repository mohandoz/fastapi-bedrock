# fastapi-bedrock — Agent Guide (template repo)

This is a **cookiecutter template**, not an application. Everything under
`{{cookiecutter.project_slug}}/` is Jinja2-rendered into a generated project;
`hooks/` run before/after generation; `cookiecutter.json` defines the options.

## Working on template files

- Directory and file names contain literal `{{cookiecutter.project_slug}}` —
  **always quote paths in shell commands**.
- Template files mix Python and Jinja2 (`{% if cookiecutter.use_x == "yes" %}`).
  Every edit must produce valid, lint-clean Python in **both** branches of
  **every** conditional it touches. `{%- ... %}` / `{% ... -%}` trim whitespace;
  check that blank lines are correct in each rendered variant.
- Literal `{{ }}` or `{% %}` that must survive rendering (e.g. GitHub Actions
  `${{ ... }}`) needs `{% raw %} ... {% endraw %}` — unless the file is listed
  in `_copy_without_render`.
- **`_copy_without_render` trap**: `.github/workflows/ci.yml` and `*.mako` are
  copied verbatim. Jinja is NEVER rendered there, so `{{ cookiecutter.* }}`
  inside them ships as literal text. Files copied verbatim also cannot vary by
  option; add new never-render files to `_copy_without_render` in
  `cookiecutter.json`.

## Hooks

- `hooks/pre_gen_project.py` validates input (`fail()` aborts, `warn()` prints).
  `RESERVED_ENTITY_NAMES` must cover any name whose rendered files would
  collide with shipped packages or static test modules.
- `hooks/post_gen_project.py` prunes files for disabled options, then runs
  `git init`, `uv sync` (skippable via `SKIP_UV_SYNC=1`) and the first commit.
  **When adding an option**: add it to `cookiecutter.json`, guard code with
  `{% if %}`, prune its files in `post_gen`, document it in the README prompt
  table, and extend the CI matrix (see below).

## Testing changes

Bake and check a variant locally (never commit baked output):

```bash
SKIP_UV_SYNC=1 uvx cookiecutter . --no-input -o "$(mktemp -d)" use_auth=yes use_mcp=yes
```

Then, inside the baked project: `uv sync && uv run ruff check . && uv run
python -m compileall -q src tests` and `uv run pytest` (needs Docker —
testcontainers). CI (`.github/workflows/test-template.yml`) bakes the
`all-on` / `all-off` / `mixed` variants, greps the output for unrendered
`cookiecutter.` strings, lints, compiles, imports the app and runs the suite.
A change is only done when every matrix variant passes.

## Conventions

- Generated code style: async everywhere, SQLModel, structlog, typed
  (`mypy --strict`), Ruff-formatted. Match it in anything you scaffold.
- The generated `AGENTS.md` (in the template dir) documents conventions for
  users of generated projects — keep it under 60 lines and in sync with any
  structural change you make here.
