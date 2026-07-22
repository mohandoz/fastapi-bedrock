{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Temporal workflows for the {{ cookiecutter.first_entity }} domain.

Workflow code must stay deterministic: no wall-clock time, randomness or I/O
(use ``workflow.now()`` / ``workflow.uuid4()`` / activities instead). Imports of
activities and shared modules go through the sandbox passthrough context manager.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from {{ cookiecutter.package_name }}.temporal.activities import process_{{ cookiecutter.first_entity }}_activity


@workflow.defn
class Process{{ entity_class }}Workflow:
    @workflow.run
    async def run(self, entity_id: str) -> str:
        return await workflow.execute_activity(
            process_{{ cookiecutter.first_entity }}_activity,
            entity_id,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=30),
                maximum_attempts=5,
            ),
        )
