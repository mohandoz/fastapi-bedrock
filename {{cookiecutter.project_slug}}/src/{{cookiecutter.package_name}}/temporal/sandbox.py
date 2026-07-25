"""Workflow sandbox configuration shared by the worker and the test suite.

Every ``Worker`` in this service must build its runner from
:func:`sandbox_runner` so the sandbox restrictions stay identical between
production workers and tests.
"""

from __future__ import annotations

from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

_RESTRICTIONS = SandboxRestrictions.default


def sandbox_runner() -> SandboxedWorkflowRunner:
    """Build the workflow runner used by every ``Worker`` in this service."""
    return SandboxedWorkflowRunner(restrictions=_RESTRICTIONS)
