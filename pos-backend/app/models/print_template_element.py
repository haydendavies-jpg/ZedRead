"""SQLAlchemy ORM model for one placed field within a PrintTemplate."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PrintTemplateElement(Base):
    """
    One field placed within a PrintTemplate, rendered as one row on the printed
    output. Elements render top-to-bottom in display_order, grouped into
    section 'header' | 'items' | 'footer' — 'items' section elements repeat
    once per invoice line item (and, for MODIFIER_LINE, once per modifier on
    that line), the rest render once.

    field_key is validated server-side against app/constants/print_fields.py's
    catalog for the parent template's template_type/section (e.g. PRODUCT_LINE
    is only valid in an 'items' section on a 'docket'/'invoice' template).

    Alignment/bold/italic/font_size are rendering hints consumed identically
    by the Android TemplateDocketRenderer (ESC/POS bytes) and the portal's
    live-preview — both built on the same padding/alignment logic so the
    preview reads as close as possible to actual printer output.
    """

    __tablename__ = "print_template_elements"
    __table_args__ = (
        CheckConstraint("section IN ('header', 'items', 'footer')", name="ck_print_template_elements_section_valid"),
        CheckConstraint(
            "font_size IN ('small', 'normal', 'large', 'xlarge')",
            name="ck_print_template_elements_font_size_valid",
        ),
        CheckConstraint(
            "alignment IN ('left', 'center', 'right', 'justify')",
            name="ck_print_template_elements_alignment_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("print_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent template — cascades deletion",
    )
    section: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="'header' | 'items' | 'footer'",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Print order within the section — lower values appear first",
    )
    field_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Catalog key from app/constants/print_fields.py, e.g. 'STORE_NAME', 'PRODUCT_LINE'",
    )
    free_text_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Only used when field_key='FREE_TEXT' — the literal text to print",
    )
    font_size: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="normal",
        server_default="normal",
        comment="'small' | 'normal' | 'large' | 'xlarge'",
    )
    alignment: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="left",
        server_default="left",
        comment="'left' | 'center' | 'right' | 'justify'",
    )
    is_bold: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_italic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
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
