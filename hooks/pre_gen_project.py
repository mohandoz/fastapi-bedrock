"""Pre-generation hook: validate user input before the project is created."""

from __future__ import annotations

import json
import keyword
import re
import sys

IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PROJECT_SLUG_RE = re.compile(r"^[a-z](?:[a-z0-9-]*[a-z0-9])?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VERSION_RE = re.compile(
    r"^[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?"
    r"(?:\.post[0-9]+)?(?:\.dev[0-9]+)?"
    r"(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?$",
    re.IGNORECASE,
)
SUPPORTED_PYTHON_VERSIONS = {"3.12", "3.13", "3.14"}

# Entity names that would collide with packages the template already ships
# (domains/auth, domains/llm, core/, api/, events/, mcp/, temporal/) or with
# static test modules (tests/test_mcp.py, tests/test_llm.py vs the rendered
# tests/test_<first_entity>.py).
RESERVED_ENTITY_NAMES = {
    "api",
    "auth",
    "cli",
    "config",
    "core",
    "errors",
    "events",
    "health",
    "http",
    "idempotency",
    "llm",
    "llm_evals",
    "llms_txt",
    "mcp",
    "migrations",
    "middleware",
    "redis",
    "settings",
    "temporal",
}

first_entity = json.loads(r'''{{ cookiecutter.first_entity | tojson }}''')
package_name = json.loads(r'''{{ cookiecutter.package_name | tojson }}''')
project_slug = json.loads(r'''{{ cookiecutter.project_slug | tojson }}''')
project_name = json.loads(r'''{{ cookiecutter.project_name | tojson }}''')
project_description = json.loads(r'''{{ cookiecutter.project_description | tojson }}''')
author_name = json.loads(r'''{{ cookiecutter.author_name | tojson }}''')
author_email = json.loads(r'''{{ cookiecutter.author_email | tojson }}''')
version = json.loads(r'''{{ cookiecutter.version | tojson }}''')
python_version = json.loads(r'''{{ cookiecutter.python_version | tojson }}''')

use_auth = json.loads(r'''{{ cookiecutter.use_auth | tojson }}''')
use_docker = json.loads(r'''{{ cookiecutter.use_docker | tojson }}''')
use_github_actions = json.loads(r'''{{ cookiecutter.use_github_actions | tojson }}''')
use_rate_limiting = json.loads(r'''{{ cookiecutter.use_rate_limiting | tojson }}''')
use_sentry = json.loads(r'''{{ cookiecutter.use_sentry | tojson }}''')
use_temporal = json.loads(r'''{{ cookiecutter.use_temporal | tojson }}''')
use_redis = json.loads(r'''{{ cookiecutter.use_redis | tojson }}''')
use_observability = json.loads(r'''{{ cookiecutter.use_observability | tojson }}''')
use_http_client = json.loads(r'''{{ cookiecutter.use_http_client | tojson }}''')
use_mcp = json.loads(r'''{{ cookiecutter.use_mcp | tojson }}''')
use_llm_example = json.loads(r'''{{ cookiecutter.use_llm_example | tojson }}''')

USE_AUTH = use_auth == "yes"
USE_DOCKER = use_docker == "yes"
USE_RATE_LIMITING = use_rate_limiting == "yes"
USE_TEMPORAL = use_temporal == "yes"
USE_REDIS = use_redis == "yes"
USE_OBSERVABILITY = use_observability == "yes"
USE_MCP = use_mcp == "yes"
USE_LLM_EXAMPLE = use_llm_example == "yes"


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

# The generated code uses PEP 695 type-parameter syntax and its dependency
# bounds are verified only for the explicitly supported minor releases.
if python_version not in SUPPORTED_PYTHON_VERSIONS:
    fail(
        f"python_version '{python_version}' is unsupported; choose one of: "
        f"{', '.join(sorted(SUPPORTED_PYTHON_VERSIONS))}."
    )

for option, value in (
    ("use_auth", use_auth),
    ("use_docker", use_docker),
    ("use_github_actions", use_github_actions),
    ("use_rate_limiting", use_rate_limiting),
    ("use_sentry", use_sentry),
    ("use_temporal", use_temporal),
    ("use_redis", use_redis),
    ("use_observability", use_observability),
    ("use_http_client", use_http_client),
    ("use_mcp", use_mcp),
    ("use_llm_example", use_llm_example),
):
    if value not in {"yes", "no"}:
        fail(f"{option} must be 'yes' or 'no', not {value!r}.")

for field, value in (
    ("project_name", project_name),
    ("project_description", project_description),
    ("author_name", author_name),
):
    if not value.strip():
        fail(f"{field} cannot be empty.")
    if "\n" in value or "\r" in value:
        fail(f"{field} must be a single line.")

max_slug_length = 47 if USE_DOCKER else 63
if not PROJECT_SLUG_RE.fullmatch(project_slug) or len(project_slug) > max_slug_length:
    fail(
        f"'{project_slug}' is not a safe project_slug. Use 1-{max_slug_length} "
        "lowercase letters, digits or hyphens, starting with a letter and "
        "ending with a letter or digit."
    )

if not EMAIL_RE.fullmatch(author_email):
    fail(f"'{author_email}' is not a valid author_email.")

if not VERSION_RE.fullmatch(version):
    fail(
        f"'{version}' is not a supported version. Use a PEP 440-compatible "
        "release such as '1.2.3', '1.2.3rc1' or '1.2.3.dev1'."
    )

if USE_DOCKER and ("+" in version or len(version) > 128):
    fail(
        f"version '{version}' cannot be used as an OCI image tag. With "
        "use_docker=yes, use at most 128 letters, digits, dots or hyphens and "
        "omit the PEP 440 local-version suffix (for example, use '1.2.3' "
        "instead of '1.2.3+local')."
    )


if not IDENTIFIER_RE.match(first_entity):
    fail(
        f"'{first_entity}' is not a valid entity name. "
        "Use lowercase snake_case, e.g. 'item' or 'blog_post'."
    )

# PostgreSQL truncates identifiers after 63 bytes. Leave room for the generated
# ``ix_<entity>s_name`` index so independently generated names cannot collide.
if len(first_entity) > 54:
    fail(f"'{first_entity}' is too long; first_entity must be at most 54 characters.")

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

if USE_AUTH and not USE_RATE_LIMITING:
    warn(
        "use_auth=yes with use_rate_limiting=no: login, password-reset and "
        "token endpoints have no built-in brute-force protection."
    )

if USE_MCP and not USE_AUTH:
    warn(
        "use_mcp=yes with use_auth=no: the MCP endpoint at /mcp is served "
        "without bearer-token verification. Do not expose it publicly without "
        "adding authentication."
    )

if USE_LLM_EXAMPLE and not USE_AUTH:
    warn(
        "use_llm_example=yes with use_auth=no: the /llm endpoints proxy a "
        "metered, paid API without authentication. Do not expose them "
        "publicly without adding authentication or strict rate limits."
    )

if USE_LLM_EXAMPLE and not USE_RATE_LIMITING:
    warn(
        "use_llm_example=yes with use_rate_limiting=no: callers can generate "
        "unbounded metered API traffic. Add an upstream quota or rate limit."
    )
