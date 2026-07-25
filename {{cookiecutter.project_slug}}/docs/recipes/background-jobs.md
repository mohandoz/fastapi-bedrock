# Background work: which tool?

{%- set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') %}

This template offers up to three ways to run work outside the request/response
cycle. They are not interchangeable — their delivery guarantees differ, and
picking the wrong one means either rebuilding retries and idempotency by hand
or dragging workflow-determinism constraints into a fire-and-forget
notification.

| You need | Use | Guarantee |
| --- | --- | --- |
| Best-effort side work after the response; losing it on a crash or deploy is acceptable | `BackgroundTasks` (built into FastAPI) | None — in-process, no retry, dies with the process |
| A side effect that must happen *iff* the transaction committed; fan-out to other consumers; integration events | Transactional outbox → Redis Streams (`use_redis`{% if cookiecutter.use_redis == "yes" %}, enabled{% else %}, **not enabled** in this project{% endif %}) | At-least-once, survives restarts, ordered per stream |
| Multi-step, long-running processes: retries with state, compensation/sagas, timers, human-in-the-loop | Temporal (`use_temporal`{% if cookiecutter.use_temporal == "yes" %}, enabled{% else %}, **not enabled** in this project{% endif %}) | Durable execution — every step is replayable and individually retried |

Worked example — "send an email after signup":

- The email is a courtesy and signup already succeeded → `BackgroundTasks`.
- Other systems (CRM sync, analytics) must also react to `user.registered`, and
  the email must not vanish if the pod dies → outbox event with an email
  handler in the consumer.
- Signup starts a provisioning sequence (create tenant → seed data → email →
  roll back on failure) → a Temporal workflow with one activity per step.

## 1. `BackgroundTasks` — request-scoped fire-and-forget

Runs in the same process after the response is sent. No retry, no persistence:
a crash, redeploy or scale-down between response and task loses the work
silently. Keep tasks short (they share the event loop and delay graceful
shutdown) and never put money-touching or must-happen work here.

```python
from uuid import UUID

import httpx
import structlog
from fastapi import BackgroundTasks

logger = structlog.get_logger(__name__)


async def notify_webhook(entity_id: UUID) -> None:
    """Best-effort notification — failures are logged, never raised."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                "https://hooks.example.com/{{ cookiecutter.first_entity }}",
                json={"id": str(entity_id)},
            )
    except httpx.HTTPError:
        logger.warning("webhook.failed", entity_id=str(entity_id))


@router.post("", response_model={{ entity_class }}Read, status_code=status.HTTP_201_CREATED)
async def create_{{ cookiecutter.first_entity }}(
    data: {{ entity_class }}Create, service: ServiceDep, background: BackgroundTasks
) -> {{ entity_class }}:
    obj = await service.create(data)
    background.add_task(notify_webhook, obj.id)
    return obj
```

**Session gotcha:** by the time a background task runs, the request's
`SessionDep` session is already committed and closed. A task that needs the
database must open its own session:

```python
from {{ cookiecutter.package_name }}.core.database import async_session_factory


async def record_audit(entity_id: UUID) -> None:
    async with async_session_factory() as session:
        ...
        await session.commit()
```
{%- if cookiecutter.use_http_client == "yes" %}

For real outbound HTTP prefer the shared resilient client (`core/http.py`,
available as `request.app.state.http_client`) over an ad-hoc `AsyncClient` —
it adds retries and a circuit breaker.
{%- endif %}

## 2. Transactional outbox → Redis Streams — reliable events
{% if cookiecutter.use_redis == "yes" %}
Use this when the side effect must happen exactly when the domain change
commits — and not when it rolls back. `enqueue_event` writes the event to the
`outbox_events` table **in the caller's transaction**; the events worker's
relay forwards committed rows to a Redis Stream (CloudEvents envelope) and a
consumer group processes them at-least-once. No dual-write race, survives any
crash.

Publish from a service, on the same session the repository uses:

```python
from {{ cookiecutter.package_name }}.events.publisher import enqueue_event


class {{ entity_class }}Service:
    async def create(self, data: {{ entity_class }}Create) -> {{ entity_class }}:
        obj = await self.repository.add({{ entity_class }}(**data.model_dump()))
        await enqueue_event(
            self.repository.session,
            "{{ cookiecutter.first_entity }}.created",
            {"id": str(obj.id)},
        )
        return obj
```

Consume by dispatching on `event_type` in `events/consumer.py:handle_event`.
Handlers **must be idempotent** — the CloudEvents `id` is stable across
redeliveries, so use it to dedupe side effects. Run the worker with
`make events-worker`{% if cookiecutter.use_docker == "yes" %} (started automatically by `docker compose up`){% endif %}.

Choose the outbox over Temporal when the producer does not care *how* the
event is handled (fan-out, integration, projections). Choose it over
`BackgroundTasks` whenever losing the work is not acceptable.
{%- else %}
Not generated in this project (`use_redis=no`). The pattern: write the event
row in the same DB transaction as the domain change, then relay committed rows
to a broker and consume them at-least-once. Re-generate with `use_redis=yes`
(or see the template's `events/` package) to get the outbox table, relay,
CloudEvents envelope and consumer-group worker ready-made.
{%- endif %}

## 3. Temporal — durable, multi-step workflows
{% if cookiecutter.use_temporal == "yes" %}
Use Temporal when the *process itself* has state: several steps that must all
happen, per-step retries, compensation on failure, timers ("remind after 7
days"), or waits for external signals. The workflow is replayable — after any
crash it resumes exactly where it stopped.

The shipped demo (`temporal/workflows.py`) is the pattern to copy: a
deterministic workflow that delegates every side effect to an activity with an
explicit `RetryPolicy`, started from the API via a stable workflow ID for
dedup (`temporal/router.py`). Extend it by adding one activity per step:

```python
@workflow.defn
class Provision{{ entity_class }}Workflow:
    @workflow.run
    async def run(self, entity_id: str) -> str:
        await workflow.execute_activity(
            reserve_resources_activity, entity_id, start_to_close_timeout=timedelta(seconds=30)
        )
        try:
            return await workflow.execute_activity(
                activate_activity, entity_id, start_to_close_timeout=timedelta(seconds=30)
            )
        except ActivityError:
            # Compensation: undo the first step, then surface the failure.
            await workflow.execute_activity(
                release_resources_activity, entity_id, start_to_close_timeout=timedelta(seconds=30)
            )
            raise
```

The cost is the determinism contract: no wall-clock time, randomness or I/O in
workflow code (use `workflow.now()`, `workflow.uuid4()` and activities), plus a
Temporal server and worker to operate. Don't pay it for a one-shot
notification — that's what the other two rows of the table are for.
{%- else %}
Not generated in this project (`use_temporal=no`). Temporal gives durable
execution: workflows that survive crashes, retry each step independently and
can wait days for timers or signals. If you find yourself hand-rolling a state
machine table with retry counters and cron sweeps, re-generate with
`use_temporal=yes` instead — the template ships a client, worker, sandboxed
workflow and activity wired end to end.
{%- endif %}
