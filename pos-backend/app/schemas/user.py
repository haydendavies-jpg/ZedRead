"""Pydantic schemas for POS user creation flows outside the SuperAdmin-only POST /users route."""

import uuid

from pydantic import BaseModel, EmailStr, model_validator


class ManagedUserCreate(BaseModel):
    """
    Payload for a management-portal (or SuperAdmin) caller creating a new User
    plus their initial access grant in one step (Users page "Add User").

    Mirrors AccessGrantCreate's scope/site_id/brand_id FK-consistency rule.
    Group scope is intentionally not offered here — a group-scope User is
    only ever the auto-created Master User (site_service.create_site()); this
    endpoint is for ordinary staff onboarded at a brand or site.
    """

    first_name: str
    last_name: str
    email: EmailStr | None = None
    password: str | None = None
    scope: str
    site_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    access_profile_id: uuid.UUID
    backend_role: str | None = None

    @model_validator(mode="after")
    def check_password_requires_email(self) -> "ManagedUserCreate":
        """A password is meaningless without a login email to attach it to."""
        if self.password is not None and self.email is None:
            raise ValueError("password requires an email")
        return self

    @model_validator(mode="after")
    def check_scope_fk_consistency(self) -> "ManagedUserCreate":
        """Ensure exactly one FK matches the scope value — site or brand only."""
        if self.scope == "site":
            if not self.site_id or self.brand_id:
                raise ValueError("scope='site' requires site_id only")
        elif self.scope == "brand":
            if not self.brand_id or self.site_id:
                raise ValueError("scope='brand' requires brand_id only")
        else:
            raise ValueError(f"scope must be 'site' or 'brand'; got '{self.scope}'")
        return self
