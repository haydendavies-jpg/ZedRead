"""Pydantic schemas for table maps & floor service (Android POS Phase 4)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.constants.table_map import SHAPE_KINDS

_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
_SHAPE_KIND_PATTERN = "^(" + "|".join(sorted(SHAPE_KINDS)) + ")$"


# ── Shapes ────────────────────────────────────────────────────────────────────


class TableMapShapeOut(BaseModel):
    """A placed shape, as stored — authoring data only, no live status."""

    id: uuid.UUID
    table_map_id: uuid.UUID
    kind: str
    label: str
    x: float
    y: float
    w: float
    h: float
    color: str | None
    is_locked: bool
    dashed: bool
    sort_order: int
    dining_table_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class TableMapShapeCreate(BaseModel):
    """Payload for adding a shape to a map. A table-kind shape also creates its DiningTable row."""

    kind: str = Field(..., pattern=_SHAPE_KIND_PATTERN)
    label: str = Field(..., min_length=1, max_length=50)
    x: float = Field(..., ge=0, le=100)
    y: float = Field(..., ge=0, le=100)
    w: float = Field(..., gt=0, le=100)
    h: float = Field(..., gt=0, le=100)
    color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)
    is_locked: bool = False
    dashed: bool = False
    sort_order: int = 0


class TableMapShapeUpdate(BaseModel):
    """Payload for repositioning/resizing/restyling a shape — all optional. kind cannot be changed."""

    label: str | None = Field(None, min_length=1, max_length=50)
    x: float | None = Field(None, ge=0, le=100)
    y: float | None = Field(None, ge=0, le=100)
    w: float | None = Field(None, gt=0, le=100)
    h: float | None = Field(None, gt=0, le=100)
    color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)
    is_locked: bool | None = None
    dashed: bool | None = None
    sort_order: int | None = None


# ── Maps ──────────────────────────────────────────────────────────────────────


class TableMapOut(BaseModel):
    """Serialised table map for list views (no nested shapes)."""

    id: uuid.UUID
    brand_id: uuid.UUID
    site_id: uuid.UUID
    name: str
    sort_order: int
    is_published: bool
    published_at: datetime | None
    grid_size: int
    is_grid_locked: bool
    is_active: bool
    shape_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TableMapDetail(TableMapOut):
    """Full table map detail — every placed shape."""

    shapes: list[TableMapShapeOut]


class TableMapCreate(BaseModel):
    """Payload for creating a table map."""

    name: str = Field(..., min_length=1, max_length=255)
    site_id: uuid.UUID
    sort_order: int = 0
    grid_size: int = Field(20, ge=1, le=100)
    is_grid_locked: bool = False


class TableMapUpdate(BaseModel):
    """Payload for updating a table map's mutable fields — all optional."""

    name: str | None = Field(None, min_length=1, max_length=255)
    sort_order: int | None = None
    grid_size: int | None = Field(None, ge=1, le=100)
    is_grid_locked: bool | None = None


# ── POS consumption contract ────────────────────────────────────────────────


class PosDiningTableStatus(TableMapShapeOut):
    """A table-kind shape plus its live DiningTable/TableSession status, for GET /pos/table-map."""

    status: str | None = None  # None means 'open' — see TableSession's class docstring
    session_id: uuid.UUID | None = None
    covers: int | None = None
    seated_at: datetime | None = None
    last_touch_at: datetime | None = None
    server_user_id: uuid.UUID | None = None
    server_name: str | None = None
    merge_partner_session_id: uuid.UUID | None = None
    merge_partner_label: str | None = None
    reserved_at: datetime | None = None
    reservation_label: str | None = None


class PosTableMapDetail(TableMapOut):
    """GET /pos/table-map's per-map response shape — every shape, table-kind ones carrying live status."""

    shapes: list[PosDiningTableStatus]


# ── Live status mutation requests ───────────────────────────────────────────


class SeatTableRequest(BaseModel):
    """Payload to seat a table — opens a new TableSession."""

    covers: int = Field(..., ge=1)
    server_user_id: uuid.UUID | None = None
    client_ref: str | None = Field(
        None, description="Client-generated idempotency key — a retried seat with the same value is deduped"
    )
    checksum: str | None = Field(
        None, description="SHA-256 over the canonical seat payload — verified if supplied"
    )


class OrderTableRequest(BaseModel):
    """Payload to mark a seated table's session as ordered."""

    checksum: str | None = Field(None, description="SHA-256 over the canonical transition payload — verified if supplied")


class BillTableRequest(BaseModel):
    """Payload to mark an ordered table's session as needing its bill."""

    checksum: str | None = Field(None, description="SHA-256 over the canonical transition payload — verified if supplied")


class MergeTableRequest(BaseModel):
    """Payload to bidirectionally merge two table sessions."""

    partner_session_id: uuid.UUID
    checksum: str | None = Field(None, description="SHA-256 over the canonical merge payload — verified if supplied")


class ClearTableRequest(BaseModel):
    """Payload to clear a table — closes its session and any merge link, returning it to 'open'."""

    checksum: str | None = Field(None, description="SHA-256 over the canonical clear payload — verified if supplied")


class ReserveTableRequest(BaseModel):
    """Payload to record a future reservation on a currently-open table."""

    reservation_label: str = Field(..., min_length=1, max_length=100)
    reserved_at: datetime


class TableSessionOut(BaseModel):
    """Serialised table session — the mutation routes' response shape."""

    id: uuid.UUID
    dining_table_id: uuid.UUID
    status: str
    covers: int
    seated_at: datetime
    last_touch_at: datetime
    server_user_id: uuid.UUID | None
    merge_partner_session_id: uuid.UUID | None
    closed_at: datetime | None
    client_ref: str | None = None
    checksum: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
