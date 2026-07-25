"""Guards against drift between ``.env.example`` and the ``Settings`` model."""

from __future__ import annotations

import re
from pathlib import Path

from {{ cookiecutter.package_name }}.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

# `KEY=value` at the start of a line; an optional leading "# " documents a
# default without setting it.
KEY_RE = re.compile(r"^(?P<comment>#\s*)?(?P<key>[A-Z][A-Z0-9_]*)=")

# Keys in .env.example that are intentionally not Settings fields.
NOT_SETTINGS = {
    # docker-compose interpolation only (db credentials + DATABASE_URLs); the
    # application itself never reads it.
    "POSTGRES_PASSWORD",
}

# Settings fields intentionally absent from .env.example: baked in at project
# generation time (metadata) or a code-level decision rather than deploy config.
NOT_DOCUMENTED = {
    "version",
    "description",
    "contact_name",
    "contact_email",
{%- if cookiecutter.use_auth == "yes" %}
    "algorithm",  # JWT signing algorithm; changing it invalidates issued tokens
{%- endif %}
}


def _example_keys() -> tuple[set[str], set[str]]:
    """Return ``(active, documented)`` keys from ``.env.example``.

    ``active`` holds uncommented ``KEY=value`` assignments; ``documented`` also
    includes commented-out defaults such as ``# DB_POOL_SIZE=5``.
    """
    active: set[str] = set()
    documented: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = KEY_RE.match(line.strip())
        if match is None:
            continue
        documented.add(match.group("key"))
        if match.group("comment") is None:
            active.add(match.group("key"))
    return active, documented


def test_every_example_key_is_a_settings_field() -> None:
    """Unknown keys would be silently ignored at runtime (extra='ignore')."""
    active, _ = _example_keys()
    fields = {name.upper() for name in Settings.model_fields}
    unknown = active - fields - NOT_SETTINGS
    assert not unknown, f".env.example keys without a Settings field: {sorted(unknown)}"


def test_every_settings_field_is_documented() -> None:
    """Every Settings field must appear in .env.example (a commented default counts)."""
    _, documented = _example_keys()
    missing = {
        name
        for name in Settings.model_fields
        if name not in NOT_DOCUMENTED and name.upper() not in documented
    }
    assert not missing, f"Settings fields missing from .env.example: {sorted(missing)}"
