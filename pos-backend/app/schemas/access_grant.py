"""Pydantic schemas for user access grant management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class AccessGrantResponse(BaseModel):
    """Full representation of a UserAccessGrant row.

    The user_* fields are populated by the list route (which joins the User
    row) so the portal grants table can show who each grant belongs to; they
    stay None on the create/update/set-default responses, which return the
    grant in isolation.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    # Identifying details of the grant's user, resolved by the list route.
    user_name: str | None = None
    user_email: str | None = None
    user_ref: str | None = None
    scope: str
    site_id: uuid.UUID | None
    brand_id: uuid.UUID | None
    group_id: uuid.UUID | None
    access_profile_id: uuid.UUID
    granted_by_id: uuid.UUID | None
    is_active: bool
    is_default: bool
    backend_role: str | None = None
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
    """
    Payload for updating an existing grant.

    Both fields are optional — supply only the one(s) you want to change.
    Presence in model_fields_set controls which fields are written, so
    sending ``{"backend_role": null}`` explicitly clears the backend role
    while omitting the key leaves the existing value unchanged.
    """

    access_profile_id: uuid.UUID | None = None
    backend_role: str | None = None


class AccessGrantBulkUpdate(BaseModel):
    """
    Payload for applying one profile and/or backend-role change to many grants.

    Same presence semantics as AccessGrantUpdate — a field is applied to every
    listed grant only if the key is present, so ``{"backend_role": null}``
    clears the role on all of them while omitting it leaves each unchanged.
    """

    grant_ids: list[uuid.UUID]
    access_profile_id: uuid.UUID | None = None
    backend_role: str | None = None


class AccessGrantBulkRevoke(BaseModel):
    """Payload for revoking many grants at once."""

    grant_ids: list[uuid.UUID]


class BulkGrantError(BaseModel):
    """One grant that could not be updated/revoked in a bulk operation."""

    grant_id: uuid.UUID
    detail: str


class AccessGrantBulkResult(BaseModel):
    """Outcome of a bulk grant operation — which succeeded and which failed.

    Partial success is allowed: grants that pass their per-grant scope, role
    ceiling, and Master-User checks are applied; the rest are reported in
    ``errors`` with the reason, so the UI can surface exactly what was skipped.
    """

    succeeded: list[uuid.UUID]
    errors: list[BulkGrantError]
