"""Pre-generation hook: validate user input before the project is created."""

from __future__ import annotations

import re
import sys

IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

first_entity = "{{ cookiecutter.first_entity }}"
package_name = "{{ cookiecutter.package_name }}"


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(1)


if not IDENTIFIER_RE.match(first_entity):
    fail(
        f"'{first_entity}' is not a valid entity name. "
        "Use lowercase snake_case, e.g. 'item' or 'blog_post'."
    )

if not IDENTIFIER_RE.match(package_name):
    fail(
        f"'{package_name}' is not a valid Python package name. "
        "Adjust the project name so the slug maps to a valid identifier."
    )
