"""Business logic for Product CRUD and photo upload.

Photo upload is handled via the upload_photo() helper which:
  - Enforces the 500 KB size limit (raises HTTP 413 if exceeded)
  - Enforces a 500x500 minimum resolution (raises HTTP 422 if too small) —
    any aspect ratio at or above that minimum is accepted; 500x500 (square)
    is only a recommendation surfaced in the portal upload UI, not enforced
  - Uploads to Supabase Storage and returns the public URL
  - Called separately from create/update so the product route can accept
    a multipart form with a JSON body + file part
"""

import io
import uuid
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

import structlog
from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    PRODUCT_BULK_UPDATED,
    PRODUCT_CREATED,
    PRODUCT_DEACTIVATED,
    PRODUCT_MODIFIER_LINKED,
    PRODUCT_PHOTO_UPDATED,
    PRODUCT_REACTIVATED,
    PRODUCT_UPDATED,
)
from app.constants.statuses import ActorType
from app.models.brand import Brand
from app.models.category import Category
from app.models.menu_button import MenuButton
from app.models.menu_layout import MenuLayout
from app.models.menu_tab import MenuTab
from app.models.modifier_group import ModifierGroup
from app.models.product_modifier_group_link import ProductModifierGroupLink
from app.models.reporting_group import ReportingGroup
from app.models.tax_category import TaxCategory
from app.models.user import User
from app.models.product import Product
from app.schemas.product import ProductBulkUpdate, ProductBulkUpdateResult, ProductCreate, ProductUpdate
from app.services.audit_service import log_action
from app.services.tax_resolution_service import country_inclusive_rate_names, derive_ex_price_cents
from app.utils.storage import extension_for_content_type, upload_image

log = structlog.get_logger(__name__)

# Maximum photo size enforced before attempting Supabase upload
_MAX_PHOTO_BYTES = 500 * 1024  # 500 KB
_ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
# Minimum resolution — a 1:1 ratio is recommended in the portal upload UI but
# not enforced here, since the requester called it a recommendation, not a rule.
_MIN_PHOTO_DIMENSION_PX = 500


def _validate_photo_dimensions(contents: bytes) -> None:
    """
    Raise HTTP 422 if the image is smaller than the 500x500 minimum.

    Args:
        contents: Raw image bytes already read from the upload.

    Raises:
        HTTPException: 422 if either dimension is below the minimum, or the
            bytes cannot be decoded as an image.
    """
    try:
        with Image.open(io.BytesIO(contents)) as image:
            width, height = image.size
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is not a valid image",
        ) from exc

    if width < _MIN_PHOTO_DIMENSION_PX or height < _MIN_PHOTO_DIMENSION_PX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Image must be at least {_MIN_PHOTO_DIMENSION_PX}x{_MIN_PHOTO_DIMENSION_PX}px "
                f"(received {width}x{height})"
            ),
        )


async def _compute_price_ex_cents(
    db: AsyncSession, brand_id: uuid.UUID, base_price_cents: int, is_taxable: bool
) -> int:
    """
    Resolve the tax-exclusive price for a product given its current taxability.

    Taxable products have GST embedded in base_price_cents (tax-inclusive) —
    the exclusive price is derived by stripping the brand's country rate.
    Tax-free products have no tax to strip: the exclusive price is exactly
    the entered price, since there is no tax component to remove.

    Args:
        db: Active database session.
        brand_id: Brand the product belongs to (resolves the country rate).
        base_price_cents: The tax-inclusive price as currently entered.
        is_taxable: Whether the product is sold with tax applied.

    Returns:
        int: The tax-exclusive price in cents.
    """
    if not is_taxable:
        return base_price_cents
    return await derive_ex_price_cents(db, brand_id, base_price_cents)


async def _get_or_404(db: AsyncSession, brand_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    """
    Fetch a Product by ID scoped to a brand, or raise HTTP 404.

    Args:
        db: Active database session.
        brand_id: Brand scope — prevents cross-brand access.
        product_id: UUID of the product to fetch.

    Returns:
        Product: The found instance.

    Raises:
        HTTPException: 404 if not found within the brand.
    """
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.brand_id == brand_id,
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


async def _validate_category(
    db: AsyncSession, brand_id: uuid.UUID, category_id: uuid.UUID
) -> None:
    """
    Raise HTTP 400 if the category does not belong to the given brand.

    Prevents assigning a product to a category from a different brand.

    Args:
        db: Active database session.
        brand_id: Expected brand owner of the category.
        category_id: UUID of the category to validate.

    Raises:
        HTTPException: 400 if the category belongs to a different brand.
        HTTPException: 404 if the category does not exist.
    """
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    if cat.brand_id != brand_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category belongs to a different brand",
        )


async def _validate_tax_category(
    db: AsyncSession, brand_id: uuid.UUID, tax_category_id: uuid.UUID
) -> None:
    """
    Raise HTTP 400/404 if the tax category does not belong to the given brand.

    Args:
        db: Active database session.
        brand_id: Expected brand owner of the tax category.
        tax_category_id: UUID of the tax category to validate.

    Raises:
        HTTPException: 404 if the tax category does not exist.
        HTTPException: 400 if it belongs to a different brand.
    """
    result = await db.execute(select(TaxCategory).where(TaxCategory.id == tax_category_id))
    tax_category = result.scalar_one_or_none()
    if tax_category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax category not found")
    if tax_category.brand_id != brand_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tax category belongs to a different brand",
        )


async def _validate_modifier_group(
    db: AsyncSession, brand_id: uuid.UUID, modifier_group_id: uuid.UUID
) -> ModifierGroup:
    """
    Fetch a ModifierGroup scoped to a brand, or raise HTTP 400/404.

    Args:
        db: Active database session.
        brand_id: Expected brand owner of the modifier group.
        modifier_group_id: UUID of the modifier group to validate.

    Returns:
        ModifierGroup: The found, brand-owned modifier group.

    Raises:
        HTTPException: 404 if the modifier group does not exist.
        HTTPException: 400 if it belongs to a different brand.
    """
    result = await db.execute(select(ModifierGroup).where(ModifierGroup.id == modifier_group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modifier group not found")
    if group.brand_id != brand_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Modifier group belongs to a different brand",
        )
    return group


async def list_products(
    db: AsyncSession,
    brand_id: uuid.UUID,
    category_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
    include_inactive: bool = False,
) -> list[tuple[Product, str, str, uuid.UUID, str, str | None, str]]:
    """
    Return a paginated list of products for a brand, joined to their Category and Reporting Group.

    The join surfaces the Category name/colour and Reporting Group id/name for the
    Stage 20 table view without denormalizing any of it onto the Product row.
    modifier_names is a comma-joined list of this product's active linked
    modifier group names (Menu Studio redesign), resolved via a correlated
    scalar subquery rather than a GROUP BY so the base product/category/
    reporting-group join stays row-per-product. tax_name is the brand's
    country tax rate name(s) (e.g. "GST") for a taxable product, or "Tax
    free" — the same rate(s) country_inclusive_rate_names/derive_ex_price_cents
    already use to split base_price_cents, resolved once per call rather than
    per row since it only varies by the brand's country, not by product.

    Args:
        db: Active database session.
        brand_id: Scope to this brand.
        category_id: Optional filter — only products in this category.
        skip: Pagination offset.
        limit: Maximum rows to return.
        include_inactive: When True, also return soft-deleted products (Stage 20 table
            view filters active/inactive client-side rather than via a repeat API call).

    Returns:
        list[tuple[Product, str, str, uuid.UUID, str, str | None, str]]: Each tuple is
            (product, category_name, category_color, reporting_group_id,
            reporting_group_name, modifier_names, tax_name), ordered by display_order then name.
    """
    modifier_names_subq = (
        select(func.string_agg(ModifierGroup.name, ", "))
        .select_from(ProductModifierGroupLink)
        .join(ModifierGroup, ProductModifierGroupLink.modifier_group_id == ModifierGroup.id)
        .where(
            ProductModifierGroupLink.product_id == Product.id,
            ModifierGroup.is_active == True,  # noqa: E712
        )
        .correlate(Product)
        .scalar_subquery()
    )
    query = (
        select(
            Product,
            Category.name,
            Category.default_color,
            Category.reporting_group_id,
            ReportingGroup.name,
            modifier_names_subq,
        )
        .join(Category, Product.category_id == Category.id)
        .join(ReportingGroup, Category.reporting_group_id == ReportingGroup.id)
        .where(Product.brand_id == brand_id)
        .order_by(Product.display_order, Product.name)
        .offset(skip)
        .limit(limit)
    )
    if not include_inactive:
        query = query.where(Product.is_active == True)  # noqa: E712
    if category_id is not None:
        query = query.where(Product.category_id == category_id)

    result = await db.execute(query)
    rows = [tuple(row) for row in result.all()]

    # Fallback for a taxable product whose brand has no inclusive tax
    # template configured — distinct from "Tax free" (is_taxable=False),
    # since the product IS charged tax-inclusive, its rate just has no name yet.
    taxed_name = "Taxed"
    if rows:
        brand_result = await db.execute(select(Brand.country).where(Brand.id == brand_id))
        country = brand_result.scalar_one_or_none()
        if country is not None:
            rate_names = await country_inclusive_rate_names(db, country)
            if rate_names:
                taxed_name = " + ".join(rate_names)

    return [
        (product, category_name, category_color, reporting_group_id, reporting_group_name, modifier_names, taxed_name if product.is_taxable else "Tax free")
        for product, category_name, category_color, reporting_group_id, reporting_group_name, modifier_names in rows
    ]


async def get_product(
    db: AsyncSession, brand_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """
    Fetch a single product by ID, scoped to the brand.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to fetch.

    Returns:
        Product: The found product.

    Raises:
        HTTPException: 404 if not found.
    """
    return await _get_or_404(db, brand_id, product_id)


async def create_product(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: ProductCreate,
    actor: User,
    import_id: uuid.UUID | None = None,
) -> Product:
    """
    Create a new product in the catalog and write an audit log row.

    Validates that the assigned category belongs to the same brand
    (cross-brand category assignment raises HTTP 400).

    Args:
        db: Active database session.
        brand_id: Brand to create the product under.
        payload: Product creation data.
        actor: The authenticated POS user performing the action.
        import_id: Batch ID shared by every row of a bulk import (Stage 19) so
            the audit trail can trace a whole upload; None for direct API calls.

    Returns:
        Product: The newly created product.

    Raises:
        HTTPException: 400 if the category belongs to a different brand.
        HTTPException: 404 if the category does not exist.
    """
    await _validate_category(db, brand_id, payload.category_id)

    price_ex_cents = await _compute_price_ex_cents(
        db, brand_id, payload.base_price_cents, payload.is_taxable
    )

    product = Product(
        id=uuid.uuid4(),
        brand_id=brand_id,
        category_id=payload.category_id,
        tax_category_id=payload.tax_category_id,
        name=payload.name,
        description=payload.description,
        print_name=payload.print_name,
        base_price_cents=payload.base_price_cents,
        price_ex_cents=price_ex_cents,
        is_taxable=payload.is_taxable,
        is_open_item=payload.is_open_item,
        display_order=payload.display_order,
        is_active=True,
    )
    db.add(product)

    after_state: dict = {
        "name": product.name,
        "category_id": str(product.category_id),
        "base_price_cents": product.base_price_cents,
    }
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=PRODUCT_CREATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state=after_state,
    )

    await db.commit()
    await db.refresh(product)
    log.info("product.created", product_id=str(product.id), brand_id=str(brand_id))
    return product


async def update_product(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductUpdate,
    actor: User,
    import_id: uuid.UUID | None = None,
) -> Product:
    """
    Update a product's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to update.
        payload: Fields to update (all optional).
        actor: The authenticated POS user performing the action.
        import_id: Batch ID shared by every row of a bulk import (Stage 19) so
            the audit trail can trace a whole upload; None for direct API calls.

    Returns:
        Product: The updated product.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 400 if the new category belongs to a different brand.
    """
    product = await _get_or_404(db, brand_id, product_id)

    if payload.category_id is not None:
        await _validate_category(db, brand_id, payload.category_id)
        product.category_id = payload.category_id

    before = {"name": product.name, "base_price_cents": product.base_price_cents}

    if payload.tax_category_id is not None:
        product.tax_category_id = payload.tax_category_id
    if payload.name is not None:
        product.name = payload.name
    if payload.description is not None:
        product.description = payload.description
    if payload.print_name is not None:
        product.print_name = payload.print_name
    if payload.base_price_cents is not None:
        product.base_price_cents = payload.base_price_cents
    if payload.is_taxable is not None:
        product.is_taxable = payload.is_taxable
    if payload.is_open_item is not None:
        product.is_open_item = payload.is_open_item
    # Re-derive the exclusive price whenever either input to the derivation
    # changes — the inclusive price, or taxability itself (switching a product
    # to Tax Free must stop stripping a rate that no longer applies, and vice
    # versa switching to Taxed must start applying the country rate).
    if payload.base_price_cents is not None or payload.is_taxable is not None:
        product.price_ex_cents = await _compute_price_ex_cents(
            db, brand_id, product.base_price_cents, product.is_taxable
        )
    if payload.display_order is not None:
        product.display_order = payload.display_order
    if payload.is_sold_out is not None:
        product.is_sold_out = payload.is_sold_out

    after_state: dict = {"name": product.name, "base_price_cents": product.base_price_cents}
    if payload.is_sold_out is not None:
        after_state["is_sold_out"] = product.is_sold_out
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=PRODUCT_UPDATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after_state,
    )

    await db.commit()
    await db.refresh(product)
    return product


async def deactivate_product(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    actor: User,
) -> Product:
    """
    Soft-delete a product by setting is_active=False.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to deactivate.
        actor: The authenticated POS user performing the action.

    Returns:
        Product: The deactivated product.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if already inactive.
    """
    product = await _get_or_404(db, brand_id, product_id)

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product is already inactive",
        )

    product.is_active = False

    await log_action(
        db=db,
        action=PRODUCT_DEACTIVATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(product)
    return product


async def set_product_active_state(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    is_active: bool,
    actor: User,
    import_id: uuid.UUID | None = None,
) -> Product:
    """
    Set a product's is_active flag directly (activate or soft-delete).

    Unlike deactivate_product(), this is idempotent — setting the flag to its
    current value is a silent no-op rather than a 409 conflict, since bulk
    imports (Stage 19) commonly re-upload a full export where most rows are
    unchanged. Used by import_service.py, and by the portal's
    POST /products/{id}/activate route (Stage 20) — the dedicated DELETE route
    keeps using deactivate_product() for its stricter 409-on-repeat semantics.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to update.
        is_active: The desired active state.
        actor: The authenticated user performing the action.
        import_id: Batch ID shared by every row of a bulk import; None for direct calls.

    Returns:
        Product: The product, with is_active set to the requested value.

    Raises:
        HTTPException: 404 if not found.
    """
    product = await _get_or_404(db, brand_id, product_id)
    if product.is_active == is_active:
        return product

    before_active = product.is_active
    product.is_active = is_active

    after_state: dict = {"is_active": is_active}
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=PRODUCT_DEACTIVATED if not is_active else PRODUCT_REACTIVATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": before_active},
        after_state=after_state,
    )

    await db.commit()
    await db.refresh(product)
    return product


async def upload_photo(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    file: UploadFile,
    actor: User,
) -> Product:
    """
    Upload a product photo to Supabase Storage and save the URL on the product.

    Enforces a 500 KB limit before attempting the upload. Raises HTTP 413 if
    the file exceeds the limit. Raises HTTP 415 if the content type is not an
    accepted image type. Raises HTTP 422 if the image is smaller than the
    500x500 minimum — any aspect ratio at or above that minimum is accepted;
    a square (1:1) image is only a recommendation, not enforced.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to attach the photo to.
        file: The uploaded image file (UploadFile from FastAPI).
        actor: The authenticated POS user performing the action.

    Returns:
        Product: The product with updated photo_url.

    Raises:
        HTTPException: 404 if the product is not found.
        HTTPException: 413 if the file exceeds 500 KB.
        HTTPException: 415 if the content type is not an accepted image type.
        HTTPException: 422 if the image is smaller than 500x500px.
    """
    product = await _get_or_404(db, brand_id, product_id)

    contents = await file.read()
    _validate_photo_dimensions(contents)
    ext = extension_for_content_type(file.content_type or "")
    photo_url = await upload_image(
        bucket="product-photos",
        path=f"products/{brand_id}/{product_id}.{ext}",
        content_type=file.content_type or "",
        contents=contents,
        allowed_content_types=_ALLOWED_PHOTO_TYPES,
        max_bytes=_MAX_PHOTO_BYTES,
    )

    old_url = product.photo_url
    product.photo_url = photo_url

    await log_action(
        db=db,
        action=PRODUCT_PHOTO_UPDATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"photo_url": old_url},
        after_state={"photo_url": photo_url},
    )

    await db.commit()
    await db.refresh(product)
    log.info("product.photo.uploaded", product_id=str(product.id))
    return product


# ── Bulk operations ────────────────────────────────────────────────────────────


async def _bulk_attach_modifier_group(
    db: AsyncSession,
    product_ids: list[uuid.UUID],
    modifier_group_id: uuid.UUID,
    actor: User,
) -> set[uuid.UUID]:
    """
    Attach modifier_group_id to every product in product_ids missing it.

    Append-only: never detaches or reorders a product's existing modifier
    links. Each new link is placed after the product's current maximum
    display_order (or 0 if it has none).

    Args:
        db: Active database session.
        product_ids: Candidate products to attach the group to.
        modifier_group_id: The modifier group to attach.
        actor: The authenticated user performing the action.

    Returns:
        set[uuid.UUID]: product_ids that received a new link.
    """
    # One query to find who already has the link, rather than N existence checks
    existing_result = await db.execute(
        select(ProductModifierGroupLink.product_id).where(
            ProductModifierGroupLink.product_id.in_(product_ids),
            ProductModifierGroupLink.modifier_group_id == modifier_group_id,
        )
    )
    already_linked = {row[0] for row in existing_result.all()}
    to_link = [pid for pid in product_ids if pid not in already_linked]
    if not to_link:
        return set()

    # One query for every product's current max display_order, rather than N
    max_orders_result = await db.execute(
        select(ProductModifierGroupLink.product_id, func.max(ProductModifierGroupLink.display_order))
        .where(ProductModifierGroupLink.product_id.in_(to_link))
        .group_by(ProductModifierGroupLink.product_id)
    )
    max_order_by_product = dict(max_orders_result.all())

    linked: set[uuid.UUID] = set()
    for product_id in to_link:
        current_max = max_order_by_product.get(product_id)
        next_order = (current_max + 1) if current_max is not None else 0
        link = ProductModifierGroupLink(
            id=uuid.uuid4(),
            product_id=product_id,
            modifier_group_id=modifier_group_id,
            display_order=next_order,
        )
        db.add(link)
        await log_action(
            db=db,
            action=PRODUCT_MODIFIER_LINKED,
            entity_type="product_modifier_group_link",
            entity_id=str(link.id),
            actor_type=ActorType.USER,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_name=actor.name,
            after_state={
                "product_id": str(product_id),
                "modifier_group_id": str(modifier_group_id),
                "via": "bulk_update",
            },
        )
        linked.add(product_id)
    return linked


async def _cascade_deactivate_products(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    ref_by_product: dict[uuid.UUID, str],
) -> dict[uuid.UUID, tuple[int, int]]:
    """
    Delete stale POS-facing rows for products archived by bulk_update_products().

    Deletes every product_modifier_group_links row for these products (an
    archived product's modifier attachments no longer mean anything), and
    every menu_buttons row (kind='product') across the brand's menu_layouts
    whose product_ref matches one of these products' ref codes — otherwise a
    stale POS button would keep pointing at a soft-deleted product.
    menu_buttons has no direct brand_id column, so it's scoped through
    tab_id -> menu_tabs.layout_id -> menu_layouts.brand_id.

    Args:
        db: Active database session.
        brand_id: Brand scope for the menu_buttons join.
        product_ids: Products being archived in this call.
        ref_by_product: Each product's `ref` code, needed to match menu_buttons.

    Returns:
        dict[uuid.UUID, tuple[int, int]]: product_id -> (deleted_modifier_link_count,
            deleted_menu_button_count), for the per-product audit rows.
    """
    if not product_ids:
        return {}

    links_result = await db.execute(
        select(ProductModifierGroupLink.id, ProductModifierGroupLink.product_id).where(
            ProductModifierGroupLink.product_id.in_(product_ids)
        )
    )
    link_ids: list[uuid.UUID] = []
    link_count_by_product: dict[uuid.UUID, int] = defaultdict(int)
    for link_id, product_id in links_result.all():
        link_ids.append(link_id)
        link_count_by_product[product_id] += 1
    if link_ids:
        await db.execute(delete(ProductModifierGroupLink).where(ProductModifierGroupLink.id.in_(link_ids)))

    refs = list(ref_by_product.values())
    buttons_result = await db.execute(
        select(MenuButton.id, MenuButton.product_ref)
        .join(MenuTab, MenuButton.tab_id == MenuTab.id)
        .join(MenuLayout, MenuTab.layout_id == MenuLayout.id)
        .where(
            MenuLayout.brand_id == brand_id,
            MenuButton.kind == "product",
            MenuButton.product_ref.in_(refs),
        )
    )
    button_ids: list[uuid.UUID] = []
    button_count_by_ref: dict[str, int] = defaultdict(int)
    for button_id, ref in buttons_result.all():
        button_ids.append(button_id)
        button_count_by_ref[ref] += 1
    if button_ids:
        await db.execute(delete(MenuButton).where(MenuButton.id.in_(button_ids)))

    return {
        product_id: (
            link_count_by_product.get(product_id, 0),
            button_count_by_ref.get(ref_by_product[product_id], 0),
        )
        for product_id in product_ids
    }


async def bulk_update_products(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: ProductBulkUpdate,
    actor: User,
) -> ProductBulkUpdateResult:
    """
    Apply one or more field changes to a set of products in one transaction.

    All-or-nothing: every product_id must belong to brand_id, and any
    reassigned category_id/tax_category_id/modifier_group_id must too — the
    whole batch is rejected with HTTP 400 before any row is touched (mirrors
    import_service.py's validate-then-upsert convention: validate everything
    up front, then write).

    Field order of operations within a product: category, price (either
    price_cents or the price_markup_percent rounded to the nearest cent via
    Decimal/ROUND_HALF_UP — never float, CLAUDE.md rule 9), tax_category_id
    (model_fields_set-aware so an explicit null clears the override), then
    is_active. modifier_group_id attaches (append-only) after every product's
    field changes are applied. Finally, if is_active is False, every selected
    product's modifier links and matching menu_buttons rows are deleted (the
    bulk archive cascade) — is_active=True only reactivates, no cascade.

    One log_action() row is written per product that actually changed (not
    one for the whole batch) so each product's own audit trail stays
    complete — a query for entity_type='product' AND entity_id=<id> shows
    every field this bulk call touched on that product, including any
    cascade-deleted link/button counts.

    Args:
        db: Active database session.
        brand_id: Brand scope — every product_id must belong to this brand.
        payload: The bulk update fields to apply.
        actor: The authenticated user performing the action.

    Returns:
        ProductBulkUpdateResult: Count and ids of the products actually modified.

    Raises:
        HTTPException: 400 if any product_id, category_id, tax_category_id,
            or modifier_group_id does not belong to this brand.
        HTTPException: 404 if category_id/tax_category_id/modifier_group_id
            does not exist at all.
    """
    # Load every requested product scoped to the brand in one query
    products_result = await db.execute(
        select(Product).where(Product.id.in_(payload.product_ids), Product.brand_id == brand_id)
    )
    products_by_id = {p.id: p for p in products_result.scalars().all()}
    missing = set(payload.product_ids) - set(products_by_id.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "One or more product_ids do not belong to this brand",
                "invalid_product_ids": sorted(str(pid) for pid in missing),
            },
        )

    # Validate every cross-brand reference before touching any row
    if payload.category_id is not None:
        await _validate_category(db, brand_id, payload.category_id)
    if payload.tax_category_id is not None:
        await _validate_tax_category(db, brand_id, payload.tax_category_id)
    modifier_group: ModifierGroup | None = None
    if payload.modifier_group_id is not None:
        modifier_group = await _validate_modifier_group(db, brand_id, payload.modifier_group_id)

    products = list(products_by_id.values())
    is_archiving = payload.is_active is False
    tax_category_field_set = "tax_category_id" in payload.model_fields_set

    # Snapshot before-state per product ahead of any mutation, for audit rows
    before_snapshots: dict[uuid.UUID, dict] = {
        product.id: {
            "category_id": str(product.category_id),
            "base_price_cents": product.base_price_cents,
            "tax_category_id": str(product.tax_category_id) if product.tax_category_id else None,
            "is_active": product.is_active,
        }
        for product in products
    }

    touched: set[uuid.UUID] = set()

    for product in products:
        if payload.category_id is not None and product.category_id != payload.category_id:
            product.category_id = payload.category_id
            touched.add(product.id)

        price_changed = False
        if payload.price_cents is not None:
            if product.base_price_cents != payload.price_cents:
                product.base_price_cents = payload.price_cents
                price_changed = True
        elif payload.price_markup_percent is not None:
            # Money arithmetic via Decimal/ROUND_HALF_UP, never float (CLAUDE.md rule 9)
            markup_multiplier = 1 + Decimal(str(payload.price_markup_percent)) / Decimal("100")
            new_price_cents = int(
                (Decimal(product.base_price_cents) * markup_multiplier).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            if new_price_cents != product.base_price_cents:
                product.base_price_cents = new_price_cents
                price_changed = True
        if price_changed:
            touched.add(product.id)
            # Re-derive the exclusive price since the inclusive price moved
            product.price_ex_cents = await _compute_price_ex_cents(
                db, brand_id, product.base_price_cents, product.is_taxable
            )

        if tax_category_field_set and product.tax_category_id != payload.tax_category_id:
            product.tax_category_id = payload.tax_category_id
            touched.add(product.id)

        if payload.is_active is not None and product.is_active != payload.is_active:
            product.is_active = payload.is_active
            touched.add(product.id)

    # Attach the modifier group before the archive cascade so a product that's
    # both newly-linked and archived in the same call still gets cleaned up
    newly_linked: set[uuid.UUID] = set()
    if modifier_group is not None:
        newly_linked = await _bulk_attach_modifier_group(
            db, [product.id for product in products], modifier_group.id, actor
        )
        touched |= newly_linked

    cascade_counts: dict[uuid.UUID, tuple[int, int]] = {}
    if is_archiving:
        ref_by_product = {product.id: product.ref for product in products}
        cascade_counts = await _cascade_deactivate_products(
            db, brand_id, [product.id for product in products], ref_by_product
        )
        # A product already inactive with nothing left to clean up is a true
        # no-op; one that still had stale links/buttons removed did change
        touched |= {pid for pid, (link_n, button_n) in cascade_counts.items() if link_n or button_n}

    for product in products:
        if product.id not in touched:
            continue
        after_state: dict = {
            "category_id": str(product.category_id),
            "base_price_cents": product.base_price_cents,
            "tax_category_id": str(product.tax_category_id) if product.tax_category_id else None,
            "is_active": product.is_active,
        }
        if product.id in newly_linked:
            after_state["modifier_group_linked"] = str(modifier_group.id)  # type: ignore[union-attr]
        if product.id in cascade_counts:
            deleted_links, deleted_buttons = cascade_counts[product.id]
            after_state["deleted_modifier_link_count"] = deleted_links
            after_state["deleted_menu_button_count"] = deleted_buttons

        await log_action(
            db=db,
            action=PRODUCT_BULK_UPDATED,
            entity_type="product",
            entity_id=str(product.id),
            actor_type=ActorType.USER,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_name=actor.name,
            before_state=before_snapshots[product.id],
            after_state=after_state,
        )

    await db.commit()
    updated_ids = sorted(touched, key=str)
    log.info("product.bulk_updated", brand_id=str(brand_id), updated_count=len(updated_ids))
    return ProductBulkUpdateResult(updated_count=len(updated_ids), updated_product_ids=updated_ids)
