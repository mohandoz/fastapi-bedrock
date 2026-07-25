# Recipe: feature flags with OpenFeature

{%- set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') %}

[OpenFeature](https://openfeature.dev/) is the CNCF-standard flag API: call
sites evaluate flags against one interface, and the backing provider (in-code
defaults, [flagd](https://flagd.dev/), LaunchDarkly, Unleash, ...) is swapped in
one place without touching them.

## 1. Install

```bash
uv add openfeature-sdk
```

## 2. The flags module

`src/{{ cookiecutter.package_name }}/core/flags.py`:

```python
"""Feature flags via the OpenFeature SDK.

Starts on the in-memory provider (flags defined in code, good enough for
trunk-based "ship dark, flip later" work). Swapping ``set_provider`` for a
real backend changes rollout behaviour everywhere without touching call sites.
"""

from __future__ import annotations

from openfeature import api
from openfeature.client import OpenFeatureClient
from openfeature.provider.in_memory_provider import InMemoryFlag, InMemoryProvider

FLAGS: dict[str, InMemoryFlag] = {
    "new-{{ cookiecutter.first_entity }}-flow": InMemoryFlag(
        default_variant="off",
        variants={"on": True, "off": False},
    ),
}


def configure_flags() -> None:
    """Install the provider. Call once, before the app serves traffic."""
    api.set_provider(InMemoryProvider(FLAGS))


def get_flags_client() -> OpenFeatureClient:
    return api.get_client("{{ cookiecutter.package_name }}")
```

## 3. Wire into the lifespan

In `main.py`'s `lifespan`, inside the `AsyncExitStack` block:

```python
from openfeature import api as openfeature_api

from {{ cookiecutter.package_name }}.core.flags import configure_flags

        configure_flags()
        stack.callback(openfeature_api.shutdown)  # let providers flush/close
```

## 4. Evaluate at the call site

Targeted evaluation keys on a stable identity so each
{% if cookiecutter.use_auth == "yes" %}user{% else %}caller{% endif %} gets a
consistent variant during percentage rollouts:

```python
from openfeature.evaluation_context import EvaluationContext

from {{ cookiecutter.package_name }}.core.flags import get_flags_client


@router.get("", response_model=Page[{{ entity_class }}Read])
async def list_{{ cookiecutter.first_entity }}s(
    service: ServiceDep,
{%- if cookiecutter.use_auth == "yes" %}
    current_user: CurrentUser,
{%- endif %}
) -> Page[{{ entity_class }}]:
    flags = get_flags_client()
    if flags.get_boolean_value(
        "new-{{ cookiecutter.first_entity }}-flow",
        False,  # the safe default when the provider is down
{%- if cookiecutter.use_auth == "yes" %}
        EvaluationContext(targeting_key=str(current_user.id)),
{%- else %}
        EvaluationContext(targeting_key="anonymous"),
{%- endif %}
    ):
        ...  # new path
    ...  # current path
```

Keep flags **short-lived**: a flag is a deferred merge conflict, so delete it
(and the losing branch) once the rollout finishes.

## 5. Graduate to a real provider

When flags need to change without a deploy, run
[flagd](https://flagd.dev/) next to the app and swap the provider:

```bash
uv add openfeature-provider-flagd
```

```python
from openfeature.contrib.provider.flagd import FlagdProvider


def configure_flags() -> None:
    api.set_provider(FlagdProvider(host="localhost", port=8013))
```
{%- if cookiecutter.use_docker == "yes" %}

For local development add flagd to `docker-compose.yml` and point it at a
mounted flag file:

```yaml
  flagd:
    image: ghcr.io/open-feature/flagd:latest
    command: ["start", "--uri", "file:/etc/flagd/flags.json"]
    ports:
      - "127.0.0.1:8013:8013"
    volumes:
      - ./flags.json:/etc/flagd/flags.json:ro
```
{%- endif %}

Hosted backends (LaunchDarkly, Unleash, PostHog, ...) each ship their own
OpenFeature provider — same one-line swap. See the
[provider ecosystem](https://openfeature.dev/ecosystem/).
