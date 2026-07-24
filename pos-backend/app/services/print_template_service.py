"""Business logic for PrintTemplate CRUD and element management.

'invoice' | 'register_summary' | 'cash_in_slip' are brand-wide singletons,
seeded once per brand (seed_default_templates, called from
brand_service.create_brand()). 'docket' templates are one-per-PrinterLocation,
created alongside their location (create_docket_template, called from
printer_location_service.create_printer_location()) — this module owns the
default-element seeding for both paths.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.audit_actions import PRINT_TEMPLATE_ELEMENTS_UPDATED, PRINT_TEMPLATE_UPDATED
from app.constants.print_fields import (
    DEFAULT_CASH_IN_SLIP_ELEMENTS,
    DEFAULT_DOCKET_ELEMENTS,
    DEFAULT_INVOICE_ELEMENTS,
    DEFAULT_REGISTER_SUMMARY_ELEMENTS,
    SECTION_PRINT_ORDER,
    is_valid_field_key,
)
from app.models.brand import Brand
from app.models.group import Group
from app.models.print_template import PrintTemplate
from app.models.print_template_element import PrintTemplateElement
from app.models.printer_location import PrinterLocation
from app.models.site import Site
from app.models.user import User
from app.schemas.print_template import (
    PosCompanyProfileOut,
    PosPrintConfigResponse,
    PrintTemplateDetail,
    PrintTemplateElementIn,
    PrintTemplateElementOut,
    PrintTemplateUpdate,
)
from app.schemas.printer_location import PrinterLocationOut
from app.services.audit_service import log_action
from app.services.branding_service import resolve_effective_logo

log = structlog.get_logger(__name__)

# (display name, default elements) for each brand-wide singleton type.
_SINGLETON_DEFAULTS: dict[str, tuple[str, list[dict]]] = {
    "invoice": ("Invoice", DEFAULT_INVOICE_ELEMENTS),
    "register_summary": ("Register Summary", DEFAULT_REGISTER_SUMMARY_ELEMENTS),
    "cash_in_slip": ("Cash-in Slip", DEFAULT_CASH_IN_SLIP_ELEMENTS),
}


def _build_elements(template_id: uuid.UUID, elements: list[dict]) -> list[PrintTemplateElement]:
    """
    Build PrintTemplateElement rows for a freshly-created template from a default-element spec list.

    Args:
        template_id: The parent template's UUID.
        elements: Default element specs from app/constants/print_fields.py.

    Returns:
        list[PrintTemplateElement]: Unpersisted ORM rows — caller adds them to the session.
    """
    return [
        PrintTemplateElement(
            id=uuid.uuid4(),
            template_id=template_id,
            section=e["section"],
            display_order=e["display_order"],
            field_key=e["field_key"],
            free_text_value=e.get("free_text_value"),
            font_size=e.get("font_size", "normal"),
            alignment=e.get("alignment", "left"),
            is_bold=e.get("is_bold", False),
            is_italic=e.get("is_italic", False),
        )
        for e in elements
    ]


async def seed_default_templates(db: AsyncSession, brand_id: uuid.UUID) -> None:
    """
    Create the three brand-wide singleton print templates with their default elements.

    Called inside brand_service.create_brand() in the same transaction — no
    commit here, the caller's own commit covers this too.

    Args:
        db: Active database session.
        brand_id: The newly-created brand to seed templates for.
    """
    for template_type, (name, default_elements) in _SINGLETON_DEFAULTS.items():
        template = PrintTemplate(id=uuid.uuid4(), brand_id=brand_id, template_type=template_type, name=name)
        db.add(template)
        db.add_all(_build_elements(template.id, default_elements))


async def create_docket_template(
    db: AsyncSession, brand_id: uuid.UUID, printer_location_id: uuid.UUID, location_name: str
) -> PrintTemplate:
    """
    Create a 'docket' PrintTemplate with default elements for a newly-created printer location.

    Called inside printer_location_service.create_printer_location() in the
    same transaction — no commit here.

    Args:
        db: Active database session.
        brand_id: The printer location's brand.
        printer_location_id: The newly-created printer location's UUID.
        location_name: The location's name, used to name its docket template.

    Returns:
        PrintTemplate: The unpersisted docket template — caller commits.
    """
    template = PrintTemplate(
        id=uuid.uuid4(),
        brand_id=brand_id,
        printer_location_id=printer_location_id,
        template_type="docket",
        name=f"{location_name} Docket",
    )
    db.add(template)
    db.add_all(_build_elements(template.id, DEFAULT_DOCKET_ELEMENTS))
    return template


async def _get_or_404(db: AsyncSession, brand_id: uuid.UUID, template_id: uuid.UUID) -> PrintTemplate:
    """
    Fetch a print template by ID, scoped to the brand, with its elements eagerly loaded.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        template_id: UUID of the template to fetch.

    Returns:
        PrintTemplate: The found template.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(PrintTemplate)
        .options(selectinload(PrintTemplate.elements))
        .where(PrintTemplate.id == template_id, PrintTemplate.brand_id == brand_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print template not found")
    return template


async def list_templates(
    db: AsyncSession, brand_id: uuid.UUID, template_type: str | None = None
) -> list[PrintTemplate]:
    """
    List print templates for a brand, optionally filtered by type.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        template_type: Optional filter — 'invoice' | 'docket' | 'register_summary' | 'cash_in_slip'.

    Returns:
        list[PrintTemplate]: Matching templates, name order.
    """
    query = select(PrintTemplate).where(PrintTemplate.brand_id == brand_id).order_by(PrintTemplate.name)
    if template_type is not None:
        query = query.where(PrintTemplate.template_type == template_type)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_template_detail(db: AsyncSession, brand_id: uuid.UUID, template_id: uuid.UUID) -> PrintTemplate:
    """
    Fetch one print template with its ordered elements.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        template_id: UUID of the template to fetch.

    Returns:
        PrintTemplate: The template, with .elements populated (unordered — sort in the route/schema layer).

    Raises:
        HTTPException: 404 if not found.
    """
    return await _get_or_404(db, brand_id, template_id)


async def update_template(
    db: AsyncSession,
    brand_id: uuid.UUID,
    template_id: uuid.UUID,
    payload: PrintTemplateUpdate,
    actor: User,
) -> PrintTemplate:
    """
    Rename a print template and write an audit log row.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        template_id: UUID of the template to rename.
        payload: The new name.
        actor: The authenticated user performing the action.

    Returns:
        PrintTemplate: The updated template.

    Raises:
        HTTPException: 404 if not found.
    """
    template = await _get_or_404(db, brand_id, template_id)
    before = {"name": template.name}
    template.name = payload.name

    await log_action(
        db=db,
        action=PRINT_TEMPLATE_UPDATED,
        entity_type="print_template",
        entity_id=str(template.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"name": template.name},
    )
    await db.commit()
    await db.refresh(template)
    return template


async def replace_elements(
    db: AsyncSession,
    brand_id: uuid.UUID,
    template_id: uuid.UUID,
    elements: list[PrintTemplateElementIn],
    actor: User,
) -> PrintTemplate:
    """
    Replace a print template's complete element list and write an audit log row.

    Whole-list replace (same shape as menu_builder_service.reorder_menu_tabs)
    rather than incremental add/remove/reorder calls — the portal editor
    always holds the full ordered list client-side and saves it in one shot.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        template_id: UUID of the template to update.
        elements: The template's new complete, ordered element list.
        actor: The authenticated user performing the action.

    Returns:
        PrintTemplate: The updated template, with .elements refreshed.

    Raises:
        HTTPException: 404 if the template doesn't exist for this brand.
        HTTPException: 422 if any element's field_key is invalid for this
            template's template_type/section.
    """
    template = await _get_or_404(db, brand_id, template_id)

    for el in elements:
        if not is_valid_field_key(template.template_type, el.section, el.field_key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{el.field_key}' is not a valid field for a {template.template_type} template's {el.section} section",
            )

    before_count = len(template.elements)
    for existing in list(template.elements):
        await db.delete(existing)
    await db.flush()

    new_rows = [
        PrintTemplateElement(
            id=uuid.uuid4(),
            template_id=template.id,
            section=el.section,
            display_order=el.display_order,
            field_key=el.field_key,
            free_text_value=el.free_text_value,
            font_size=el.font_size,
            alignment=el.alignment,
            is_bold=el.is_bold,
            is_italic=el.is_italic,
        )
        for el in elements
    ]
    db.add_all(new_rows)

    await log_action(
        db=db,
        action=PRINT_TEMPLATE_ELEMENTS_UPDATED,
        entity_type="print_template",
        entity_id=str(template.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"element_count": before_count},
        after_state={"element_count": len(new_rows)},
    )
    await db.commit()
    await db.refresh(template, attribute_names=["elements"])
    return template


def _combine_address(site: Site) -> str:
    """Join a site's address fields into one printable line, skipping blanks."""
    parts = [site.address_street, site.address_city, site.address_state, site.address_postcode]
    return ", ".join(p for p in parts if p)


async def get_pos_print_config(db: AsyncSession, site: Site) -> PosPrintConfigResponse:
    """
    Assemble the full print-config sync payload for one site: printer
    locations, every print template (with elements) for the site's brand,
    and the resolved company-profile fields — the POS read contract Android
    fetches once per sync (see class docstring).

    Args:
        db: Active database session.
        site: The site to resolve print config for.

    Returns:
        PosPrintConfigResponse: Locations, templates, and company-profile fields.
    """
    brand_result = await db.execute(select(Brand).where(Brand.id == site.brand_id))
    brand = brand_result.scalar_one()
    group_result = await db.execute(select(Group).where(Group.id == brand.group_id))
    group = group_result.scalar_one_or_none()

    logo = await resolve_effective_logo(db, site)
    # tax_id_value (ABN) has no dedicated resolver like logo_url/billing_email —
    # walk site -> brand -> group by hand, same fallback order.
    abn = site.tax_id_value or brand.tax_id_value or (group.tax_id_value if group else None)

    locations_result = await db.execute(
        select(PrinterLocation).where(PrinterLocation.brand_id == brand.id, PrinterLocation.is_active == True)  # noqa: E712
    )
    locations = list(locations_result.scalars().all())

    templates_result = await db.execute(
        select(PrintTemplate)
        .options(selectinload(PrintTemplate.elements))
        .where(PrintTemplate.brand_id == brand.id)
    )
    templates = list(templates_result.scalars().all())

    return PosPrintConfigResponse(
        printer_locations=[PrinterLocationOut.model_validate(loc) for loc in locations],
        templates=[
            PrintTemplateDetail(
                id=t.id,
                brand_id=t.brand_id,
                printer_location_id=t.printer_location_id,
                template_type=t.template_type,
                name=t.name,
                created_at=t.created_at,
                updated_at=t.updated_at,
                elements=[
                    PrintTemplateElementOut.model_validate(e)
                    for e in sorted(t.elements, key=lambda e: (SECTION_PRINT_ORDER[e.section], e.display_order))
                ],
            )
            for t in templates
        ],
        company_profile=PosCompanyProfileOut(
            logo_url=logo.value,
            brand_name=brand.name,
            store_name=site.name,
            address=_combine_address(site),
            phone=site.phone_number,
            abn=abn,
        ),
    )
