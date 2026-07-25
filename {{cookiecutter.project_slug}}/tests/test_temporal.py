{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Tests for the Temporal workflow and activity."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.testing import ActivityEnvironment
from temporalio.worker import Worker

from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}
from {{ cookiecutter.package_name }}.temporal import activities as activities_module
from {{ cookiecutter.package_name }}.temporal.activities import process_{{ cookiecutter.first_entity }}_activity
from {{ cookiecutter.package_name }}.temporal.sandbox import sandbox_runner
from {{ cookiecutter.package_name }}.temporal.workflows import Process{{ entity_class }}Workflow


async def test_process_activity(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with session_factory() as db_session:
        obj = {{ entity_class }}(name="to-process")
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)
        entity_id = obj.id

    # Point the activity's session factory at the test database.
    monkeypatch.setattr(activities_module, "async_session_factory", session_factory)
    result = await ActivityEnvironment().run(process_{{ cookiecutter.first_entity }}_activity, str(entity_id))
    assert result == f"processed {{ cookiecutter.first_entity }} {entity_id}"


async def test_process_workflow_e2e() -> None:
    from temporalio.testing import WorkflowEnvironment

    try:
        env = await WorkflowEnvironment.start_time_skipping()
    except Exception as err:
        pytest.skip(f"Temporal test server unavailable: {err}")

    @activity.defn(name="process_{{ cookiecutter.first_entity }}_activity")
    async def process_mock(entity_id: str) -> str:
        return f"processed {{ cookiecutter.first_entity }} {entity_id}"

    task_queue = f"tq-{uuid.uuid4()}"
    async with (
        env,
        Worker(
            env.client,
            task_queue=task_queue,
            workflows=[Process{{ entity_class }}Workflow],
            activities=[process_mock],
            workflow_runner=sandbox_runner(),
        ),
    ):
        result = await env.client.execute_workflow(
            Process{{ entity_class }}Workflow.run,
            "abc",
            id=f"wf-{uuid.uuid4()}",
            task_queue=task_queue,
        )
    assert result == "processed {{ cookiecutter.first_entity }} abc"
