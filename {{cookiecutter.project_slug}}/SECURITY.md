# Security policy

## Supported versions

The latest released version of {{ cookiecutter.project_name }} receives security fixes.

## Reporting a vulnerability

Please report security issues **privately** — email {{ cookiecutter.author_email }}, or use
GitHub's private vulnerability reporting. Do not open a public issue for a security
problem. We aim to acknowledge reports within a few business days and will coordinate
a fix and disclosure with you.

## Secrets management

- `.env` is for **local development only**. It is gitignored{% if cookiecutter.use_docker == "yes" %} and excluded from
  the Docker image via `.dockerignore`{% endif %}; production must not depend on it.
- Environment variables work everywhere but leak easily: `kubectl describe pod`,
  crash reports and child processes all see them.
- Preferred: **file-mounted secrets**. Mount each secret as a file under
  `/run/secrets/<setting_name>` (Docker secrets and Kubernetes Secret volumes
  both do this) and pydantic-settings picks it up natively via `secrets_dir`
  in `core/config.py` — no code changes per secret.
{%- if cookiecutter.use_docker == "yes" %}
- `deploy/k8s/secret.yaml` shows the pattern. In production, sync that Secret
  from your secret manager with [External Secrets Operator](https://external-secrets.io)
  or the Secrets Store CSI driver instead of applying secrets by hand.
{%- endif %}
- Never bake secrets into images or pass them as build arguments; both persist
  in layer history.

## Backups and restore
{% if cookiecutter.use_docker == "yes" %}
`make db-backup` dumps the compose database to `backups/<timestamp>.dump`
(pg_dump custom format); `make db-restore f=backups/<file>.dump` restores it.
Note that `make docker-down` runs `docker compose down -v` and **destroys the
data volume** — back up first.
{%- if cookiecutter.use_temporal == "yes" %}

The compose Postgres instance also holds the `temporal` and
`temporal_visibility` databases, so losing the volume erases workflow history
as well.
{%- endif %}
{%- else %}
Back up with `pg_dump --format=custom` against the database from
`DATABASE_URL` and restore with `pg_restore --clean --if-exists`.
{%- endif %}

Production databases need **scheduled dumps and point-in-time recovery**
(managed Postgres provides both) before this service handles real data —
`alembic downgrade` is a schema tool, not a recovery path.

## Production posture checklist

Configuration that is unsafe outside local development already fails at boot
(see the README's production checklist). Deployment posture on top of that:

- [ ] Image pinned by digest{% if cookiecutter.use_docker == "yes" %} (see the Dockerfile header){% endif %} and scanned in CI.
- [ ] Containers run as non-root with a read-only root filesystem and all
      capabilities dropped{% if cookiecutter.use_docker == "yes" %} — `deploy/k8s/deployment.yaml` encodes this{% endif %}.
{%- if cookiecutter.use_docker == "yes" %}
- [ ] `ALLOWED_HOSTS` lists explicit hostnames **plus `localhost`**, which the
      container healthcheck and Kubernetes probes rely on.
{%- else %}
- [ ] `ALLOWED_HOSTS` lists explicit hostnames, plus `localhost` if anything
      probes the service locally.
{%- endif %}
- [ ] Migrations run from a single one-shot step per release{% if cookiecutter.use_docker == "yes" %}
      (`deploy/k8s/migration-job.yaml`){% endif %}, never in app entrypoints.
- [ ] Secrets are file-mounted and sourced from a secret manager, not
      committed manifests or plain env vars.
- [ ] Database backups are scheduled and a restore has been rehearsed.
- [ ] `make audit` (dependency CVE scan) runs in CI, not just locally.
