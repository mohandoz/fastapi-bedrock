# Deployment

Minimal, production-shaped Kubernetes manifests in `k8s/`. They encode the
runtime contract the image expects — probe paths, graceful-shutdown timing,
non-root security context and file-mounted secrets — and are meant to be
adapted, not applied verbatim.

| File | Purpose |
| --- | --- |
| `k8s/namespace.yaml` | Dedicated namespace |
| `k8s/configmap.yaml` | Non-secret settings, injected via `envFrom` |
| `k8s/secret.yaml` | Example Secret, mounted as files under `/run/secrets` |
| `k8s/deployment.yaml` | API pods: probes, resources, securityContext, drain timing |
| `k8s/service.yaml` | ClusterIP service (port 80 → 8000) |
| `k8s/migration-job.yaml` | One-shot `alembic upgrade head` per release |
| `k8s/kustomization.yaml` | Ties it together; single place to set the image |

## Release flow

```bash
docker build -t registry.example.com/{{ cookiecutter.project_slug }}:{{ cookiecutter.version }} .
docker push registry.example.com/{{ cookiecutter.project_slug }}:{{ cookiecutter.version }}

# Job specs are immutable — delete the previous run before re-applying.
kubectl -n {{ cookiecutter.project_slug }} delete job {{ cookiecutter.project_slug }}-migrate --ignore-not-found
kubectl apply -k deploy/k8s
kubectl -n {{ cookiecutter.project_slug }} wait --for=condition=complete \
    job/{{ cookiecutter.project_slug }}-migrate --timeout=120s
kubectl -n {{ cookiecutter.project_slug }} rollout status deployment/{{ cookiecutter.project_slug }}
```

## Migrations

The migration Job is the only place schema changes run — never in app pod
entrypoints, where replicas race each other. Because old pods keep serving
while the Deployment rolls, write migrations to be backward-compatible with
the previous release (expand → migrate → contract); with that discipline the
Job and the rollout can safely proceed in parallel.

## Secrets

`k8s/secret.yaml` is a hand-applied example. In production, sync the Secret
from your secret manager (External Secrets Operator or the Secrets Store CSI
driver) — see SECURITY.md for the full secrets policy.
{%- if cookiecutter.use_redis == "yes" or cookiecutter.use_temporal == "yes" %}

## Workers

Workers reuse the API image with a different command; copy `k8s/deployment.yaml`,
drop the ports/probes/Service (workers expose no HTTP), and keep the
securityContext and secrets mount:
{% if cookiecutter.use_redis == "yes" %}
- Events worker: `command: ["python", "-m", "{{ cookiecutter.package_name }}.events.worker"]`
{%- endif %}
{%- if cookiecutter.use_temporal == "yes" %}
- Temporal worker: `command: ["python", "-m", "{{ cookiecutter.package_name }}.temporal.worker"]`
{%- endif %}
{%- endif %}
