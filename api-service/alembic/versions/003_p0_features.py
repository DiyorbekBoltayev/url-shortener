"""P0 features: folders, utm_templates, retarget_pixels, link_pixels, bulk_jobs + urls columns.

Revision ID: 003_p0_features
Revises: 002_long_url_trigram_and_dns_token
Create Date: 2026-04-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003_p0_features"
down_revision = "002_long_url_trigram_and_dns_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- folders -----------------------------------------------------
    op.create_table(
        "folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("folders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_folders_workspace", "folders", ["workspace_id"])
    op.create_index("idx_folders_parent", "folders", ["parent_id"])
    op.execute("""
        CREATE TRIGGER trg_folders_updated_at
            BEFORE UPDATE ON folders
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ---- utm_templates ----------------------------------------------
    op.create_table(
        "utm_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("utm_source", sa.String(255)),
        sa.Column("utm_medium", sa.String(255)),
        sa.Column("utm_campaign", sa.String(255)),
        sa.Column("utm_term", sa.String(255)),
        sa.Column("utm_content", sa.String(255)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_utm_templates_workspace", "utm_templates", ["workspace_id"])

    # ---- retarget_pixels + link_pixels ------------------------------
    op.create_table(
        "retarget_pixels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("pixel_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_retarget_pixels_workspace", "retarget_pixels", ["workspace_id"])

    op.create_table(
        "link_pixels",
        sa.Column("url_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("urls.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("pixel_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("retarget_pixels.id", ondelete="CASCADE"), primary_key=True),
    )

    # ---- bulk_jobs ---------------------------------------------------
    op.create_table(
        "bulk_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total", sa.Integer, server_default=sa.text("0")),
        sa.Column("done", sa.Integer, server_default=sa.text("0")),
        sa.Column("failed", sa.Integer, server_default=sa.text("0")),
        sa.Column("params", postgresql.JSONB),
        sa.Column("result_url", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_bulk_jobs_workspace_status",
        "bulk_jobs",
        ["workspace_id", "status", sa.text("created_at DESC")],
    )

    # ---- urls new columns -------------------------------------------
    op.add_column("urls", sa.Column("folder_id", postgresql.UUID(as_uuid=True),
                                    sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True))
    op.add_column("urls", sa.Column("routing_rules", postgresql.JSONB, nullable=True))
    op.add_column("urls", sa.Column("qr_style", postgresql.JSONB, nullable=True))
    op.add_column("urls", sa.Column("preview_enabled", sa.Boolean, nullable=False,
                                    server_default=sa.text("FALSE")))
    op.add_column("urls", sa.Column("og_title", sa.Text, nullable=True))
    op.add_column("urls", sa.Column("og_description", sa.Text, nullable=True))
    op.add_column("urls", sa.Column("og_image_url", sa.Text, nullable=True))
    op.add_column("urls", sa.Column("favicon_url", sa.Text, nullable=True))
    op.add_column("urls", sa.Column("og_fetched_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("urls", sa.Column("safety_status", sa.String(16), nullable=False,
                                    server_default=sa.text("'unchecked'")))
    op.add_column("urls", sa.Column("safety_reason", sa.Text, nullable=True))
    op.add_column("urls", sa.Column("safety_checked_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_index("idx_urls_folder", "urls", ["workspace_id", "folder_id"])
    op.create_index("idx_urls_safety", "urls", ["safety_status"],
                    postgresql_where=sa.text("safety_status <> 'ok'"))


def downgrade() -> None:
    op.drop_index("idx_urls_safety", table_name="urls")
    op.drop_index("idx_urls_folder", table_name="urls")
    for col in ("safety_checked_at", "safety_reason", "safety_status", "og_fetched_at",
                "favicon_url", "og_image_url", "og_description", "og_title",
                "preview_enabled", "qr_style", "routing_rules", "folder_id"):
        op.drop_column("urls", col)
    op.drop_table("bulk_jobs")
    op.drop_table("link_pixels")
    op.drop_table("retarget_pixels")
    op.drop_table("utm_templates")
    op.execute("DROP TRIGGER IF EXISTS trg_folders_updated_at ON folders")
    op.drop_table("folders")
