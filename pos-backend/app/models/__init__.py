"""ORM model registry — import all models here so Alembic autogenerate detects them."""

from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.group import Group
from app.models.portal_user import PortalUser
from app.models.site import Site

__all__ = ["AuditLog", "Brand", "Group", "PortalUser", "Site"]
