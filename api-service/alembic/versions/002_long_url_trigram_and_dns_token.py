"""pg_trgm GIN indexes on urls.long_url / short_code + domains.dns_token.

Revision ID: 002_long_url_trgm
Revises: 001_initial
Create Date: 2026-04-14

RV8 H1: without a GIN trigram index, the ``ILIKE '%q%'`` search in
``list_urls`` degenerates to a seqscan on the 1M-row ``urls`` table.
This migration adds the required indexes concurrently (so it runs
safely on a live DB) and adds the ``dns_token`` column the FE expects
on the domains resource.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_long_url_trgm"
down_revision: str | None = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm was installed in 001; make sure it's present on fresh DBs
    # that used Alembic-only bootstrap.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # CONCURRENTLY requires running outside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_urls_long_url_trgm "
            "ON urls USING gin (long_url gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_urls_short_code_trgm "
            "ON urls USING gin (short_code gin_trgm_ops)"
        )

    # FE expects a `dns_token` on DomainOut — add column lazily.
    op.add_column(
        "domains",
        sa.Column("dns_token", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("domains", "dns_token")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_urls_short_code_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_urls_long_url_trgm")
