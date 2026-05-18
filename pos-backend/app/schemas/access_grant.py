"""Pydantic schemas for user access grant management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class AccessGrantResponse(BaseModel):
    """Full representation of a UserAccessGrant row."""

    id: uuid.UUID
    user_id: uuid.UUID
    scope: str
    site_id: uuid.UUID | None
    brand_id: uuid.UUID | None
    group_id: uuid.UUID | None
    access_profile_id: uuid.UUID
    granted_by_id: uuid.UUID | None
    is_active: bool
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccessGrantCreate(BaseModel):
    """
    Payload for creating a new access grant.

    Exactly one of site_id, brand_id, or group_id must be set and must
    match the scope field. Validation is enforced at the model level.
    """

    user_id: uuid.UUID
    scope: str
    site_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    access_profile_id: uuid.UUID

    @model_validator(mode="after")
    def check_scope_fk_consistency(self) -> "AccessGrantCreate":
        """Ensure exactly one FK matches the scope value."""
        if self.scope == "site":
            if not self.site_id or self.brand_id or self.group_id:
                raise ValueError("scope='site' requires site_id only")
        elif self.scope == "brand":
            if not self.brand_id or self.site_id or self.group_id:
                raise ValueError("scope='brand' requires brand_id only")
        elif self.scope == "group":
            if not self.group_id or self.site_id or self.brand_id:
                raise ValueError("scope='group' requires group_id only")
        else:
            raise ValueError(f"scope must be 'site', 'brand', or 'group'; got '{self.scope}'")
        return self


class AccessGrantUpdate(BaseModel):
    """Payload for updating the access profile on an existing grant."""

    access_profile_id: uuid.UUID
