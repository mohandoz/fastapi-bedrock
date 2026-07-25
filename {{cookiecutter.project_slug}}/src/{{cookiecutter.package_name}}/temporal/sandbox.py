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

{%- if cookiecutter.use_mcp == "yes" %}

# fastmcp's transitive dependency py-key-value-aio calls beartype_this_package()
# at import time, installing a beartype.claw hook on sys.meta_path. Any process
# that imports the MCP stack before constructing a Worker (the API process, the
# test suite) then trips that hook when the default workflow sandbox re-imports
# the workflows module: the sandboxed re-import of beartype is only partially
# initialised and beartype.claw circular-imports ("cannot import name claw_state
# from partially initialized module beartype.claw._clawstate"). Passing both
# packages through to the host interpreter avoids the re-import while keeping
# sandbox isolation for everything else.
_RESTRICTIONS = SandboxRestrictions.default.with_passthrough_modules("beartype", "key_value")
{%- else %}

_RESTRICTIONS = SandboxRestrictions.default
{%- endif %}


def sandbox_runner() -> SandboxedWorkflowRunner:
    """Build the workflow runner used by every ``Worker`` in this service."""
    return SandboxedWorkflowRunner(restrictions=_RESTRICTIONS)
