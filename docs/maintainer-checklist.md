# Maintainer checklist

One-time repository setup that cannot ship as files in the repo — run these
with the [GitHub CLI](https://cli.github.com/) as the repository owner. Items
are ordered; later ones assume earlier ones are done.

## 1. Repo metadata (discoverability + Amazon Bedrock disambiguation)

"fastapi bedrock" search results are dominated by AWS Bedrock projects, so
the description must disambiguate and the topics must never contain a bare
`bedrock`:

```bash
gh repo edit mohandoz/fastapi-bedrock \
  --description "Production-ready FastAPI + DDD cookiecutter template: async SQLModel, JWT auth, Temporal, transactional outbox events, OpenTelemetry. Not related to Amazon Bedrock." \
  --homepage "https://mohandoz.github.io/fastapi-bedrock/"

gh repo edit mohandoz/fastapi-bedrock \
  --add-topic fastapi \
  --add-topic fastapi-template \
  --add-topic fastapi-boilerplate \
  --add-topic cookiecutter \
  --add-topic cookiecutter-template \
  --add-topic python \
  --add-topic domain-driven-design \
  --add-topic sqlmodel \
  --add-topic uv \
  --add-topic cruft
```

## 2. Social preview image

No CLI support — generate a 1280×640 PNG from the logo and upload it under
**Settings → General → Social preview**:

```bash
# any SVG rasteriser works; e.g. librsvg
brew install librsvg
rsvg-convert -w 1280 -h 640 --keep-aspect-ratio --page-width 1280 --page-height 640 \
  --top 190 --left 280 assets/logo.svg -o /tmp/social-preview.png
```

## 3. Enable Discussions

The issue forms route "questions about my generated project" to Discussions,
so enable it before publicising the forms:

```bash
gh repo edit mohandoz/fastapi-bedrock --enable-discussions
```

Create a pinned welcome discussion in a Q&A category pointing at the docs
site and the issue forms.

## 4. Activate GitHub Pages (docs site)

The `Docs` workflow (`.github/workflows/docs.yml`) pushes the built
mkdocs-material site to the `gh-pages` branch. After its first successful run
on `main`:

```bash
gh api -X POST repos/mohandoz/fastapi-bedrock/pages \
  -f "source[branch]=gh-pages" -f "source[path]=/"
```

(or **Settings → Pages → Deploy from a branch → `gh-pages` / root**). The
site then serves at <https://mohandoz.github.io/fastapi-bedrock/>, including
`/llms.txt` and `/llms-full.txt` for AI assistants.

## 5. Demo repository (continuously rendered showcase)

The `Sync demo` workflow (`.github/workflows/sync-demo.yml`) renders the
default configuration and force-pushes it to a public demo repo on every
merge to `main`. It is inert until configured:

```bash
# 5.1 create the public demo repo
gh repo create mohandoz/fastapi-bedrock-demo --public \
  --description "Rendered default output of the fastapi-bedrock cookiecutter template (auto-synced; do not PR here)"

# 5.2 create a fine-grained PAT (Settings → Developer settings) scoped to
#     ONLY mohandoz/fastapi-bedrock-demo with Contents: Read and write,
#     then store it and the target repo on the template repo:
gh secret set DEMO_REPO_TOKEN --repo mohandoz/fastapi-bedrock
gh variable set DEMO_REPO --repo mohandoz/fastapi-bedrock --body "mohandoz/fastapi-bedrock-demo"

# 5.3 first sync + mark as a template repo ("Use this template" button)
gh workflow run sync-demo.yml --repo mohandoz/fastapi-bedrock
gh repo edit mohandoz/fastapi-bedrock-demo --template

# 5.4 point evaluators at it
gh repo edit mohandoz/fastapi-bedrock-demo \
  --homepage "https://mohandoz.github.io/fastapi-bedrock/" \
  --add-topic fastapi --add-topic fastapi-template --add-topic cookiecutter
```

Tag pushes (`v*`) on the template repo are mirrored to the demo repo, so
tag-to-tag diffs of the demo double as per-release upgrade notes.

## 6. One-click deploy listings (from the demo repo)

- **Railway** — publish a template from the dashboard
  (<https://railway.com/new/template> → *Create template*): one web service
  built from `mohandoz/fastapi-bedrock-demo`'s Dockerfile plus a PostgreSQL
  database; set `SECRET_KEY`, `DATABASE_URL` (reference the DB plugin) and
  `ENVIRONMENT=staging`. Published templates earn a kickback and give the
  README a "Deploy on Railway" button.
- **Render** — add a `render.yaml` blueprint to the demo repo (a web service
  from the Dockerfile plus a managed PostgreSQL), then link
  `https://render.com/deploy?repo=https://github.com/mohandoz/fastapi-bedrock-demo`
  as a "Deploy to Render" button.

Because the demo repo is force-pushed by the sync workflow, keep such
deploy-only files in the template itself (so they survive re-renders) or
accept re-adding them after workflow changes.

## 7. Submit to lists

- PR the template into the *Boilerplate* section of
  [mjhea0/awesome-fastapi](https://github.com/mjhea0/awesome-fastapi).
- Answer the recurring "which FastAPI template" threads with the comparison
  table (README → *How it compares*) rather than a bare link.

## 8. Releases

Tag releases (`git tag v0.x.y && git push --tags`) and write release notes
against the CHANGELOG; the docs' upgrade guide and the demo-repo tag diffs
both key off tags.
