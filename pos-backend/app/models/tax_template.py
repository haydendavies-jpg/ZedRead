"""Admin-owned tax template — jurisdiction-scoped tax definitions.

Templates are managed exclusively in the SuperAdmin portal and are never
exposed to management-portal (customer) users. At sale time the invoice
engine resolves the rates that apply to a site by matching its location
against every active template: a template applies when EVERY jurisdiction
field it has set matches the site (unset template fields are ignored).

Examples:
    country=AU                          → applies to every Australian site
    country=US, state=TX                → applies to every Texan site
    country=US, state=TX, county=Travis → applies only in Travis County

Rates from all matching templates combine additively by default; a rate's
tax_model marks it inclusive/exclusive/compound (see tax_calculation_service).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaxTemplate(Base):
    """A jurisdiction-scoped tax definition managed in the admin portal."""

    __tablename__ = "tax_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable label, e.g. 'Australia GST'",
    )
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        index=True,
        comment="ISO 3166-1 alpha-2 country code — the only required jurisdiction field",
    )
    state: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="State/province — NULL means the template applies country-wide",
    )
    county: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="County/region — NULL means the template applies state-wide",
    )
    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="City/suburb — NULL means the template applies county-wide",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when soft-deleted; inactive templates never match any site",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
