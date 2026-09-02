# Deployment

Minimal, production-shaped Kubernetes manifests in `k8s/`. They encode the
runtime contract the image expects — probe paths, graceful-shutdown timing,
non-root security context and file-mounted secrets — and are meant to be
adapted, not applied verbatim.

| File | Purpose |
| --- | --- |
| `k8s/common/` | Namespace, non-secret settings and example file-mounted Secret |
| `k8s/deployment.yaml` | API pods: probes, resources, securityContext, drain timing |
| `k8s/service.yaml` | ClusterIP service (port 80 → 8000) |
| `k8s/migration/` | Migration-first overlay with one-shot `alembic upgrade head` Job |
| `k8s/kustomization.yaml` | API{% if cookiecutter.use_redis == "yes" %} + events worker{% endif %}{% if cookiecutter.use_temporal == "yes" %} + Temporal worker{% endif %} overlay |

## Release flow

```bash
docker build -t registry.example.com/{{ cookiecutter.project_slug }}:{{ cookiecutter.version }} .
docker push registry.example.com/{{ cookiecutter.project_slug }}:{{ cookiecutter.version }}

# Provision {{ cookiecutter.project_slug }}-secrets from your secret manager
# before the first release. common/secret.yaml is a rejected-placeholder example
# and is deliberately NOT part of either Kustomize overlay.

# Migration first. Job specs are immutable, so delete the previous run.
kubectl -n {{ cookiecutter.project_slug }} delete job {{ cookiecutter.project_slug }}-migrate --ignore-not-found
kubectl apply -k deploy/k8s/migration
kubectl -n {{ cookiecutter.project_slug }} wait --for=condition=complete \
    job/{{ cookiecutter.project_slug }}-migrate --timeout=600s

# Only roll out code after its schema is ready.
kubectl apply -k deploy/k8s
kubectl -n {{ cookiecutter.project_slug }} rollout status deployment/{{ cookiecutter.project_slug }}
```

## Migrations

The migration Job is the only place schema changes run — never in app pod
entrypoints, where replicas race each other. It completes before the Deployment
is applied. Old pods keep serving during that first phase, so migrations must
remain backward-compatible with the previous release (expand → migrate →
contract).

## Secrets

`k8s/common/secret.yaml` is a hand-applied example and is not included by
Kustomize. In production, sync the Secret
from your secret manager (External Secrets Operator or the Secrets Store CSI
driver) — see SECURITY.md for the full secrets policy.
{%- if cookiecutter.use_redis == "yes" or cookiecutter.use_temporal == "yes" %}

## Workers

Workers reuse the API image with a different command and ship as dedicated,
hardened Deployments in the application overlay:
{% if cookiecutter.use_redis == "yes" %}
- `k8s/events-worker.yaml`: outbox relay + Redis Streams consumer.
{%- endif %}
{%- if cookiecutter.use_temporal == "yes" %}
- `k8s/temporal-worker.yaml`: Temporal workflow/activity worker.
{%- endif %}
{%- endif %}
