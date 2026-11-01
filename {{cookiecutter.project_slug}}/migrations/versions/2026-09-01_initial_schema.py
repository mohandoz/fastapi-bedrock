"""Create the initial application schema.

This is the base for a freshly generated project. Do not graft it into an
existing project's independent Alembic history; keep that history and create a
normal forward revision instead.

Revision ID: 20260901_0001
Revises:
Create Date: 2026-09-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
{% if cookiecutter.use_redis == "yes" -%}
from sqlalchemy.dialects import postgresql
{%- endif %}

revision: str = "20260901_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "{{ cookiecutter.first_entity }}s",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_{{ cookiecutter.first_entity }}s")),
    )
    op.create_index(
        op.f("ix_{{ cookiecutter.first_entity }}s_name"),
        "{{ cookiecutter.first_entity }}s",
        ["name"],
        unique=False,
    )
{%- if cookiecutter.use_auth == "yes" %}

    op.create_table(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
{%- if cookiecutter.use_redis == "no" %}

    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(length=32), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_refresh_tokens")),
    )
    op.create_index(
        op.f("ix_refresh_tokens_family"), "refresh_tokens", ["family"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False
    )
{%- endif %}
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}

    op.create_table(
        "outbox_events",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        op.f("ix_outbox_events_event_type"),
        "outbox_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_published_at"),
        "outbox_events",
        ["published_at"],
        unique=False,
    )
{%- endif %}


def downgrade() -> None:
{%- if cookiecutter.use_redis == "yes" %}
    op.drop_index(op.f("ix_outbox_events_published_at"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_event_type"), table_name="outbox_events")
    op.drop_table("outbox_events")
{%- endif %}
{%- if cookiecutter.use_auth == "yes" and cookiecutter.use_redis == "no" %}
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
{%- endif %}
{%- if cookiecutter.use_auth == "yes" %}
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
{%- endif %}
    op.drop_index(
        op.f("ix_{{ cookiecutter.first_entity }}s_name"),
        table_name="{{ cookiecutter.first_entity }}s",
    )
    op.drop_table("{{ cookiecutter.first_entity }}s")
