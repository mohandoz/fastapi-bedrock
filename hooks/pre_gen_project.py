"""Pre-generation hook: validate user input before the project is created."""

from __future__ import annotations

import re
import sys

IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

first_entity = "{{ cookiecutter.first_entity }}"
package_name = "{{ cookiecutter.package_name }}"
python_version = "{{ cookiecutter.python_version }}"


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(1)


# The generated code uses PEP 695 type-parameter syntax (and modern typing),
# which requires Python 3.12+.
try:
    major, minor = (int(part) for part in python_version.split(".")[:2])
except ValueError:
    fail(f"'{python_version}' is not a valid python_version (expected e.g. '3.13').")
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

if not IDENTIFIER_RE.match(package_name):
    fail(
        f"'{package_name}' is not a valid Python package name. "
        "Adjust the project name so the slug maps to a valid identifier."
    )
