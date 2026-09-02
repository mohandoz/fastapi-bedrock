{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Demo endpoint: start a Temporal workflow that processes a {{ cookiecutter.first_entity }}."""

from __future__ import annotations

from uuid import UUID

{% if cookiecutter.use_auth == "yes" -%}
from fastapi import APIRouter, Depends, status
{%- else -%}
from fastapi import APIRouter, status
{%- endif %}
from temporalio.common import WorkflowIDConflictPolicy

from {{ cookiecutter.package_name }}.core.config import settings
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth.dependencies import get_current_active_user
{%- endif %}
from {{ cookiecutter.package_name }}.temporal.client import TemporalClient
from {{ cookiecutter.package_name }}.temporal.workflows import Process{{ entity_class }}Workflow

router = APIRouter(
    prefix="/temporal",
    tags=["temporal"],
{%- if cookiecutter.use_auth == "yes" %}
    dependencies=[Depends(get_current_active_user)],
{%- endif %}
)


@router.post(
    "/{{ cookiecutter.first_entity }}s/{entity_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a workflow that processes a {{ cookiecutter.first_entity }}",
)
async def start_process_{{ cookiecutter.first_entity }}(entity_id: UUID, client: TemporalClient) -> dict[str, str]:
    handle = await client.start_workflow(
        Process{{ entity_class }}Workflow.run,
        str(entity_id),
        id=f"process-{{ cookiecutter.first_entity }}-{entity_id}",  # stable id -> dedup
        task_queue=settings.temporal_task_queue,
        # Attach to the running workflow instead of raising WorkflowAlreadyStartedError.
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )
    return {"workflow_id": handle.id, "run_id": handle.first_execution_run_id or ""}
