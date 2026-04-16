"""Initial schema — mirrors infrastructure/db/init.sql (HLA 3.1).

Revision ID: 001_initial
Revises:
Create Date: 2026-04-14

This migration is idempotent with the SQL bootstrap shipped by the
infrastructure repo (``/docker-entrypoint-initdb.d/init.sql``). In CI
environments that start from an empty Postgres (no init.sql), running
``alembic upgrade head`` reproduces the same schema.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("is_verified", sa.Boolean, server_default=sa.text("false")),
        sa.Column("plan", sa.String(20), server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_users_email", "users", ["email"])

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan", sa.String(20), server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_workspaces_owner_id", "workspaces", ["owner_id"])
    op.create_index("idx_workspaces_slug", "workspaces", ["slug"])

    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_workspace_members_user_id", "workspace_members", ["user_id"])

    op.create_table(
        "domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(255), unique=True, nullable=False),
        sa.Column("is_verified", sa.Boolean, server_default=sa.text("false")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("ssl_status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_domains_domain", "domains", ["domain"])
    op.create_index("idx_domains_workspace_id", "domains", ["workspace_id"])

    op.create_table(
        "urls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("short_code", sa.String(10), unique=True, nullable=False),
        sa.Column("long_url", sa.Text, nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="SET NULL")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("domains.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("max_clicks", sa.Integer),
        sa.Column("tags", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("utm_source", sa.String(255)),
        sa.Column("utm_medium", sa.String(255)),
        sa.Column("utm_campaign", sa.String(255)),
        sa.Column("click_count", sa.BigInteger, server_default="0"),
        sa.Column("last_clicked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_urls_user_id", "urls", ["user_id"])
    op.create_index("idx_urls_workspace_id", "urls", ["workspace_id"])
    op.create_index("idx_urls_domain_id", "urls", ["domain_id"])
    op.create_index("idx_urls_created_at", "urls", [sa.text("created_at DESC")])
    op.create_index(
        "idx_urls_expires_at", "urls", ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index("idx_urls_tags", "urls", ["tags"], postgresql_using="gin")
    op.create_index("idx_urls_long_url_hash", "urls", [sa.text("md5(long_url)")])

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("key_prefix", sa.String(10), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String), server_default="{read,write}"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("idx_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("idx_api_keys_workspace_id", "api_keys", ["workspace_id"])

    op.create_table(
        "webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret", sa.String(255), nullable=False),
        sa.Column("events", postgresql.ARRAY(sa.String), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_triggered", sa.DateTime(timezone=True)),
        sa.Column("failure_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_webhooks_workspace_id", "webhooks", ["workspace_id"])

    op.create_table(
        "short_code_pool",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("is_used", sa.Boolean, server_default=sa.text("false")),
        sa.Column("claimed_by", sa.String(50)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "idx_pool_available", "short_code_pool", ["is_used"],
        postgresql_where=sa.text("is_used = false"),
    )


def downgrade() -> None:
    for table in (
        "short_code_pool",
        "webhooks",
        "api_keys",
        "urls",
        "domains",
        "workspace_members",
        "workspaces",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
