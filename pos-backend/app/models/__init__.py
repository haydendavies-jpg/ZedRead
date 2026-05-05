"""ORM model registry — import all models here so Alembic autogenerate detects them."""

from app.models.access_profile import AccessProfile
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.category import Category
from app.models.group import Group
from app.models.license import License
from app.models.license_invoice import LicenseInvoice
from app.models.portal_user import PortalUser
from app.models.pos_device import PosDevice
from app.models.pos_user import POSUser
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.models.user_invite import UserInvite
from app.models.user_pin import UserPIN
from app.models.user_pos_session import UserPOSSession

__all__ = [
    "AccessProfile",
    "AuditLog",
    "Brand",
    "Category",
    "Group",
    "License",
    "LicenseInvoice",
    "PortalUser",
    "PosDevice",
    "POSUser",
    "Site",
    "UserAccessGrant",
    "UserInvite",
    "UserPIN",
    "UserPOSSession",
]
