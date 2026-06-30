"""Add company profile fields to groups, brands, and sites.

Part of the company-profile feature: timezone, currency, country, and an
optional tax ID are required independently at every level of the hierarchy
(no Group->Brand->Site inheritance for these two — confirmed with the
user). logo_url and billing_email *do* inherit child-overrides-parent, so
they stay nullable everywhere and the inheritance walk lives in
branding_service.py, not the schema. Sites additionally get a street
address, since a Site is a physical location.

Existing rows are backfilled with sensible Australia-based defaults since
timezone/currency/country are NOT NULL on tables that already have data.

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

# Backfill defaults for existing rows — sensible starting point, editable after creation.
_DEFAULT_TIMEZONE = "Australia/Sydney"
_DEFAULT_CURRENCY = "AUD"
_DEFAULT_COUNTRY = "AU"

_PROFILE_TABLES = ("groups", "brands", "sites")


def upgrade() -> None:
    """Add timezone/currency/country/tax_id_value/logo_url/billing_email to
    groups, brands, sites, plus address fields on sites only."""
    for table in _PROFILE_TABLES:
        op.add_column(table, sa.Column("timezone", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("currency", sa.String(3), nullable=True))
        op.add_column(table, sa.Column("country", sa.String(2), nullable=True))
        op.add_column(table, sa.Column("tax_id_value", sa.String(50), nullable=True))
        op.add_column(table, sa.Column("logo_url", sa.String(500), nullable=True))
        op.add_column(table, sa.Column("billing_email", sa.String(255), nullable=True))

        op.execute(
            f"UPDATE {table} SET timezone = '{_DEFAULT_TIMEZONE}', "
            f"currency = '{_DEFAULT_CURRENCY}', country = '{_DEFAULT_COUNTRY}'"
        )

        op.alter_column(table, "timezone", nullable=False)
        op.alter_column(table, "currency", nullable=False)
        op.alter_column(table, "country", nullable=False)

    op.add_column("sites", sa.Column("address_street", sa.String(255), nullable=True))
    op.add_column("sites", sa.Column("address_state", sa.String(100), nullable=True))
    op.add_column("sites", sa.Column("address_postcode", sa.String(20), nullable=True))

    op.execute(
        "UPDATE sites SET address_street = '', address_state = '', address_postcode = ''"
    )

    op.alter_column("sites", "address_street", nullable=False)
    op.alter_column("sites", "address_state", nullable=False)
    op.alter_column("sites", "address_postcode", nullable=False)


def downgrade() -> None:
    """Drop the company profile columns added in upgrade()."""
    op.drop_column("sites", "address_postcode")
    op.drop_column("sites", "address_state")
    op.drop_column("sites", "address_street")

    for table in _PROFILE_TABLES:
        op.drop_column(table, "billing_email")
        op.drop_column(table, "logo_url")
        op.drop_column(table, "tax_id_value")
        op.drop_column(table, "country")
        op.drop_column(table, "currency")
        op.drop_column(table, "timezone")
