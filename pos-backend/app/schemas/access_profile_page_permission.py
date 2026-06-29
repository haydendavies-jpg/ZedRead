"""Pydantic schemas for the page-category permission hierarchy (ROLE_MODEL.md §4)."""

import uuid

from pydantic import BaseModel


class PagePermissionsResponse(BaseModel):
    """The set of page keys currently granted to an AccessProfile."""

    access_profile_id: uuid.UUID
    page_keys: list[str]


class PagePermissionGrant(BaseModel):
    """Payload to grant or revoke a single page on an AccessProfile."""

    page_key: str


class VisiblePagesResponse(BaseModel):
    """Pages visible to a profile at a site, after the license gate is applied."""

    access_profile_id: uuid.UUID
    site_id: uuid.UUID
    page_keys: list[str]
