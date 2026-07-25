"""Pre-generation hook: validate user input before the project is created."""

from __future__ import annotations

import keyword
import re
import sys

IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Entity names that would collide with packages the template already ships
# (domains/auth, domains/llm, core/, api/, events/, mcp/, temporal/) or with
# static test modules (tests/test_mcp.py, tests/test_llm.py vs the rendered
# tests/test_<first_entity>.py).
RESERVED_ENTITY_NAMES = {"api", "auth", "core", "events", "llm", "mcp", "temporal"}

first_entity = "{{ cookiecutter.first_entity }}"
package_name = "{{ cookiecutter.package_name }}"
python_version = "{{ cookiecutter.python_version }}"

USE_AUTH = "{{ cookiecutter.use_auth }}" == "yes"
USE_DOCKER = "{{ cookiecutter.use_docker }}" == "yes"
USE_RATE_LIMITING = "{{ cookiecutter.use_rate_limiting }}" == "yes"
USE_TEMPORAL = "{{ cookiecutter.use_temporal }}" == "yes"
USE_REDIS = "{{ cookiecutter.use_redis }}" == "yes"
USE_OBSERVABILITY = "{{ cookiecutter.use_observability }}" == "yes"
USE_MCP = "{{ cookiecutter.use_mcp }}" == "yes"


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(1)


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


# Free-threaded (no-GIL) builds such as '3.14t': SQLAlchemy's asyncio bridge
# runs on greenlet, which does not support free-threaded CPython — the
# interpreter re-enables the GIL (or the greenlet install fails outright),
# silently defeating the point of choosing 3.14t. Revisit once SQLAlchemy
# 2.1's free-threading accommodations land.
_normalized_python = python_version.strip().lower()
if _normalized_python.endswith("t") or "free-threaded" in _normalized_python:
    fail(
        f"python_version '{python_version}' selects a free-threaded (no-GIL) "
        "build, which this template does not support: SQLAlchemy async "
        "requires greenlet, and greenlet does not run on free-threaded "
        "CPython. Use a standard build (e.g. '3.14') and scale with multiple "
        "uvicorn workers instead."
    )

# The generated code uses PEP 695 type-parameter syntax (and modern typing),
# which requires Python 3.12+. Ruff's target-version and mypy's python_version
# only accept MAJOR.MINOR, so patch-level input (e.g. '3.13.1') is rejected.
try:
    major, minor = (int(part) for part in python_version.split("."))
except ValueError:
    fail(
        f"'{python_version}' is not a valid python_version "
        "(expected MAJOR.MINOR, e.g. '3.13')."
    )
else:
    if (major, minor) < (3, 12):
        fail(
            f"python_version '{python_version}' is unsupported; this template requires "
            "Python 3.12 or newer (it uses PEP 695 generics)."
        )


if not IDENTIFIER_RE.match(first_entity):
    fail(
        f"'{first_entity}' is not a valid entity name. "
        "Use lowercase snake_case, e.g. 'item' or 'blog_post'."
    )

if keyword.iskeyword(first_entity) or keyword.issoftkeyword(first_entity):
    fail(
        f"'{first_entity}' is a reserved Python keyword and cannot be used "
        "as an entity name."
    )

if first_entity in RESERVED_ENTITY_NAMES:
    fail(
        f"'{first_entity}' collides with a package the template already provides. "
        f"Reserved entity names: {', '.join(sorted(RESERVED_ENTITY_NAMES))}."
    )

if not IDENTIFIER_RE.match(package_name):
    fail(
        f"'{package_name}' is not a valid Python package name. "
        "Adjust the project name so the slug maps to a valid identifier."
    )

if keyword.iskeyword(package_name) or keyword.issoftkeyword(package_name):
    fail(
        f"'{package_name}' is a reserved Python keyword and cannot be used "
        "as a package name."
    )


if not USE_DOCKER:
    for enabled, option in (
        (USE_TEMPORAL, "use_temporal"),
        (USE_REDIS, "use_redis"),
        (USE_OBSERVABILITY, "use_observability"),
    ):
        if enabled:
            warn(
                f"{option}=yes with use_docker=no: no docker-compose.yml is "
                "generated, so you must provide that infrastructure yourself."
            )

if USE_RATE_LIMITING and not USE_REDIS:
    warn(
        "use_rate_limiting=yes with use_redis=no: limits are tracked in-memory "
        "per process and are not shared across workers or replicas."
    )

if USE_MCP and not USE_AUTH:
    warn(
        "use_mcp=yes with use_auth=no: the MCP endpoint at /mcp is served "
        "without bearer-token verification. Do not expose it publicly without "
        "adding authentication."
    )
