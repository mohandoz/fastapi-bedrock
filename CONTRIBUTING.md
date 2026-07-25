# Contributing to fastapi-bedrock

Thanks for helping improve the template! This guide covers the workflows that
are specific to maintaining a *cookiecutter template* — they differ from
contributing to a normal Python project.

> Contributing to a **project generated from** this template? That project has
> its own `CONTRIBUTING.md`. Questions about your generated project belong in
> [Discussions](https://github.com/mohandoz/fastapi-bedrock/discussions), not
> the issue tracker.

## Repository layout

| Path | What it is |
| ---- | ---------- |
| `cookiecutter.json` | The prompts: variables, defaults, `_copy_without_render` |
| `hooks/` | `pre_gen_project.py` (input validation) and `post_gen_project.py` (pruning disabled features, `git init`, `uv sync`) |
| `{{cookiecutter.project_slug}}/` | The template payload — everything a generated project receives |
| `docs/` + `mkdocs.yml` | This repo's documentation site (mkdocs-material) |
| `.github/workflows/` | Template CI: the bake matrix, docs deploy, demo sync |

## Render the template locally

Every change must be verified against *rendered output*, not just the
template source:

```bash
# default configuration
uvx cookiecutter . --no-input --output-dir /tmp/bake

# a specific variant (any variable can be overridden)
uvx cookiecutter . --no-input --output-dir /tmp/bake \
  use_temporal=yes use_redis=yes use_observability=yes

# skip dependency installation for a fast render
SKIP_UV_SYNC=1 uvx cookiecutter . --no-input --output-dir /tmp/bake
```

Then run the generated project's own checks:

```bash
cd /tmp/bake/fastapi-ddd-service
make check        # ruff + mypy --strict + pytest (needs Docker for testcontainers)
```

## The rule of every branch

The nine `use_*` flags mean a change can render into hundreds of
combinations. CI (`.github/workflows/test-template.yml`) bakes three
representative variants — **all-on**, **all-off** and **mixed** — on two
Python versions, lints, type-checks, imports and (for all-on) tests them, and
greps the output for unrendered `cookiecutter.` fragments.

When you touch anything inside a `{% if %}` block, make sure **both** branches
still render valid, lint-clean code — including imports that are only used in
one branch, trailing commas, and blank-line counts (Ruff checks formatting on
rendered output). If a file must disappear when a flag is off, add it to the
corresponding `remove(...)` call in `hooks/post_gen_project.py`.

## Jinja gotchas

- **Literal braces** in template files must be escaped:
  `{{ '{prefix}' }}` renders `{prefix}`; wrap larger blocks in
  `{% raw %} ... {% endraw %}`.
- **GitHub Actions syntax** (`${{ ... }}`) collides with Jinja. The generated
  CI workflow is listed in `_copy_without_render` in `cookiecutter.json`;
  files added there are copied verbatim and must NOT contain cookiecutter
  variables.
- **Whitespace control** matters: `{%- ... -%}` trims newlines. Check rendered
  output for accidental blank lines — `ruff format --check` in the bake job
  will catch them, but locally is faster.
- The template directory name itself contains literal braces
  (`{{cookiecutter.project_slug}}`), so **quote paths** in shell commands.

## Docs site

```bash
uvx --with 'mkdocs-material>=9.7' --with 'mkdocs-llmstxt>=0.5' mkdocs serve
```

The site (this `docs/` directory) deploys to GitHub Pages on merge to `main`.
Recipes that ship *inside generated projects* live in
`{{cookiecutter.project_slug}}/docs/recipes/` instead — they may use
`{{ cookiecutter.package_name }}` and are rendered at generation time.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):
`<type>(<scope>): <imperative summary>` — e.g.
`feat(template): add use_redis outbox events` or `fix(hooks): reject keyword
entity names`. Breaking template changes (renamed variables, removed files
that `cruft update` users will hit) get a `!` and an explanation in the body.

## Pull request checklist

- [ ] Rendered at least the default configuration locally and ran `make check`
      in the output.
- [ ] Any new conditional renders correctly with the flag both on and off.
- [ ] Files for disabled features are pruned in `hooks/post_gen_project.py`.
- [ ] New variables documented in the README prompt table and
      `docs/options.md`.
- [ ] No unescaped literal `{{` / `{%` in template payload files.
- [ ] CI (`Test template`) is green.

## Reporting issues

Use the issue forms — one for template bugs, one for feature requests. For a
bug, the *exact generation command* (all overrides) plus the template commit
(from your project's `.cruft.json`) makes the difference between a
ten-minute fix and a guessing game. Security reports: please use
[private vulnerability reporting](https://github.com/mohandoz/fastapi-bedrock/security/advisories/new)
instead of public issues.

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
