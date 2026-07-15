"""Routes for POS device registration (portal authenticated)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.pos_device import PosDeviceRegister, PosDeviceResponse
from app.services import pos_device_service
from app.utils.dependencies import get_current_superadmin

router = APIRouter(prefix="/pos-devices", tags=["pos-devices"])


@router.get("/", response_model=list[PosDeviceResponse])
async def list_devices(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(get_current_superadmin),
) -> list[PosDeviceResponse]:
    """List all registered POS devices with pagination."""
    return await pos_device_service.list_devices(db, skip=skip, limit=limit)


@router.get("/{device_id}", response_model=PosDeviceResponse)
async def get_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(get_current_superadmin),
) -> PosDeviceResponse:
    """Fetch a single POS device by ID."""
    return await pos_device_service.get_device(db, device_id)


@router.post("/", response_model=PosDeviceResponse, status_code=201)
async def register_device(
    payload: PosDeviceRegister,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> PosDeviceResponse:
    """Register a new Android POS terminal under a site and license."""
    return await pos_device_service.register_device(db, payload, actor)


@router.post("/{device_id}/deregister", response_model=PosDeviceResponse)
async def deregister_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> PosDeviceResponse:
    """Deregister a POS device — marks it inactive without deleting the record."""
    return await pos_device_service.deregister_device(db, device_id, actor)
