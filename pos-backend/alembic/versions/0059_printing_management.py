"""Printing management — printer_locations, print_templates, print_template_elements.

New printer_locations table (PRN-000001 ref sequence, same mechanism as every
other entity's ref column), print_templates (a template is either one of
three brand-wide singletons — invoice/register_summary/cash_in_slip, enforced
by a partial unique index — or a per-PrinterLocation 'docket' template, one
each, enforced by printer_location_id's own unique constraint), and
print_template_elements (the ordered, alignable rows a template renders).
Also adds products.printer_location_id (which docket a product groups under)
and sites.phone_number (a Company Profile field, requested as a printable
field with no existing column anywhere in the hierarchy).

Revision ID: 0059
Revises: 0058
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create printing tables and add products.printer_location_id / sites.phone_number."""
    op.execute("CREATE SEQUENCE IF NOT EXISTS printer_locations_ref_seq START 1 INCREMENT 1")

    op.create_table(
        "printer_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ref",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text("'PRN-' || LPAD(nextval('printer_locations_ref_seq')::text, 6, '0')"),
            comment="Human-readable reference ID, e.g. PRN-000001",
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("copy_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint("copy_count >= 1", name="ck_printer_locations_copy_count_min"),
    )
    op.create_index("ix_printer_locations_brand_id", "printer_locations", ["brand_id"])

    op.create_table(
        "print_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "printer_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("printer_locations.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            comment="Set only when template_type='docket' — one docket template per location",
        ),
        sa.Column("template_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_print_templates_brand_id", "print_templates", ["brand_id"])
    # Partial unique index: the three singleton types get at most one row per
    # brand; 'docket' templates are excluded here since they're uniqued by
    # printer_location_id instead (one brand may have many docket templates).
    op.create_index(
        "uq_print_templates_brand_singleton_type",
        "print_templates",
        ["brand_id", "template_type"],
        unique=True,
        postgresql_where=sa.text("template_type != 'docket'"),
    )

    op.create_table(
        "print_template_elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("print_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(10), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("field_key", sa.String(50), nullable=False),
        sa.Column("free_text_value", sa.Text(), nullable=True),
        sa.Column("font_size", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("alignment", sa.String(10), nullable=False, server_default="left"),
        sa.Column("is_bold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_italic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint("section IN ('header', 'items', 'footer')", name="ck_print_template_elements_section_valid"),
        sa.CheckConstraint(
            "font_size IN ('small', 'normal', 'large', 'xlarge')",
            name="ck_print_template_elements_font_size_valid",
        ),
        sa.CheckConstraint(
            "alignment IN ('left', 'center', 'right', 'justify')",
            name="ck_print_template_elements_alignment_valid",
        ),
    )
    op.create_index("ix_print_template_elements_template_id", "print_template_elements", ["template_id"])

    op.add_column(
        "products",
        sa.Column(
            "printer_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("printer_locations.id", ondelete="SET NULL"),
            nullable=True,
            comment="Which order-docket print station this product groups under; NULL prints on no docket",
        ),
    )
    op.create_index("ix_products_printer_location_id", "products", ["printer_location_id"])

    op.add_column(
        "sites",
        sa.Column(
            "phone_number",
            sa.String(30),
            nullable=True,
            comment="Site's own phone number — Company Profile field, printable on receipts/dockets.",
        ),
    )


def downgrade() -> None:
    """Drop printing tables and the products/sites columns added above."""
    op.drop_column("sites", "phone_number")

    op.drop_index("ix_products_printer_location_id", table_name="products")
    op.drop_column("products", "printer_location_id")

    op.drop_index("ix_print_template_elements_template_id", table_name="print_template_elements")
    op.drop_table("print_template_elements")

    op.drop_index("uq_print_templates_brand_singleton_type", table_name="print_templates")
    op.drop_index("ix_print_templates_brand_id", table_name="print_templates")
    op.drop_table("print_templates")

    op.drop_index("ix_printer_locations_brand_id", table_name="printer_locations")
    op.drop_table("printer_locations")
    op.execute("DROP SEQUENCE IF EXISTS printer_locations_ref_seq")
