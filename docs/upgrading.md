# Upgrading generated projects with cruft

A cookiecutter template normally helps you once, on day one.
[cruft](https://cruft.github.io/cruft/) extends that to the whole life of the
project: it records which template commit a project was generated from and can
later replay template improvements onto your codebase as a reviewable diff.

## Generate with cruft

```bash
uvx cruft create gh:mohandoz/fastapi-bedrock
```

This behaves exactly like `cookiecutter`, plus it writes a `.cruft.json` at
the project root recording the template URL, the answers you gave and the
template commit. Commit that file.

## Check and update

```bash
uvx cruft check    # exit 1 if the project is behind the template
uvx cruft diff     # preview what an update would change
uvx cruft update   # apply upstream template changes as a local diff
```

`cruft update` re-renders the old and new template revisions with your
recorded answers and applies the difference to your working tree. Review it
like any other change:

1. Inspect `git diff` — the update touches only files the template owns.
2. Resolve any `*.rej` files: these are hunks that no longer applied cleanly
   because you modified the same lines. Apply the intent by hand, then delete
   the `.rej`.
3. Run `make check` (Ruff, mypy, tests).
4. Commit, e.g. `chore: apply fastapi-bedrock template update`.

## Excluding files you have diverged from

If you have rewritten a file and never want template updates to touch it
again, add it to the `skip` list in `.cruft.json`:

```json
{
  "template": "https://github.com/mohandoz/fastapi-bedrock",
  "skip": ["README.md", "Makefile"]
}
```

## Linking an existing project

Projects generated with plain `cookiecutter` have no `.cruft.json`, but you
can adopt cruft after the fact:

```bash
uvx cruft link gh:mohandoz/fastapi-bedrock
```

cruft asks for the answers you originally gave and which template commit the
project matches; be accurate here or the first `cruft update` diff will be
noisy.

## Changing answers later

Answers are recorded in `.cruft.json` under `context.cookiecutter`. To change
one (for example flipping `use_observability` on), edit the value and run
`uvx cruft update` — the diff then includes everything that flag adds. Flags
that *remove* modules work the same way in reverse, though you should verify
nothing of yours imports the removed code.

## Release-to-release upgrade notes

Template releases are tagged. The
[CHANGELOG and release notes](https://github.com/mohandoz/fastapi-bedrock/releases)
describe what changed between tags, and the demo repository (a continuously
rendered default configuration) lets you read tag-to-tag diffs of *generated
output* — often the quickest way to see what an update will do to your
project before running it.

### Initial migration compatibility

Freshly generated projects include an option-aware initial Alembic revision.
If an older generated project already has any real file in
`migrations/versions/`, do **not** graft the template's
`2026-09-01_initial_schema.py` in as a second base revision: keep your existing
history and omit that incoming file from the cruft update. Add future model
changes as normal forward revisions.

If an older project has no Alembic history but has a database created by local
`create_all`, first compare that database with the current SQLModel metadata and
establish a reviewed baseline for that existing schema. Applying the new
create-table revision directly would fail on the existing tables; stamping an
unverified schema would hide drift. New/empty databases can apply the shipped
revision normally with `make migrate`.
