# ZedRead — Target User & Role Model

**Status: target design, not yet implemented.** This document defines the intended naming and permission
model for identity in ZedRead. `ARCHITECTURE_MAP.md` and `DATA_MODEL.md` describe what the code does
*today* (`PortalUser`, `POSUser`, `backend_role`); this doc describes where that's heading. Treat the two
as separate sources of truth until the rename/role-model work is scheduled into a stage (see
`CLAUDE.md` rollout table) and implemented — at which point this document becomes ground truth and
`ARCHITECTURE_MAP.md`/`DATA_MODEL.md` get updated to match the code.

---

## 1. SuperAdmin (target rename of "Portal User")

**Purpose:** ZedRead's own staff and reseller/partner staff only. Used exclusively to access the
ZedRead admin portal to create and manage Group/Brand/Site accounts. A SuperAdmin is **never** a
customer identity and is never assigned to a Group/Brand/Site — it has no tenant scope, same as today's
`PortalUser`.

**Roles:**

| Role | Definition |
|---|---|
| Admin | Full ZedRead administrative access. |
| Reseller Staff | Partner-side staff. Exact restriction set is an open question — see §5. |

**Mapping to existing schema:** `portal_users.role` (today `super_admin \| admin \| reseller`) becomes
`admin \| reseller_staff`. "Super Admin" as a role name is retired — "Admin" is the top role *within* the
SuperAdmin user type, so the distinct "super_admin" vs "admin" split collapses to one `admin` value.

---

## 2. User (target rename of "POS User")

**Purpose:** the actual account/tenant identity — what ZedRead's customers and their staff are. A User
always has POS login. Backend/portal access (to manage Group/Brand/Site configuration) is optional and
granted per scope.

**This is already architecturally supported today** — it does not need new tables, just a rename and
some new constraints:
- Identity rows live in one table per account, scoped at the **Group** level (today's `pos_users`,
  target name `users`).
- Site assignment happens via the existing grant join table (today's `user_access_grants`, scope
  site/brand/group), with `is_default` marking the user's default site.
- Per-grant `backend_role` already gates portal/config access independently of POS access — this is
  exactly the "optional backend access" behaviour described below.

### Required fields (target — not yet enforced in schema)

| Field | Rule |
|---|---|
| First name, Last name | Required for every User except Master User (see below). |
| PIN | Required for every User except Master User. |
| Email | Optional, **unless** the user has backend access granted — then required. |
| Backend password | Only required if a backend access permission is set on at least one grant. |

### Roles and defaults

| Role | POS access | Backend access default | Notes |
|---|---|---|---|
| **Master User** | Full, fixed | N/A — identity is tied to the site itself | Exactly one per site. Access level is immutable and cannot be promoted away from or removed from its site (prevents a customer ever locking themselves out of a site). Display name is the **site's name**, not a person's name — no independent first/last name or PIN. |
| **Admin** | Unlimited, cannot be restricted | On by default, can be disabled | |
| **Reporting Only** | N/A (role is backend-oriented) | On by default | View-only: reports and invoices. No edit access to products, menus, or config by default — can be granted later. |
| **Manager** | Full by default, can be optionally restricted | Off by default, optional | |
| **Staff** | Limited by default, can be expanded | Off by default, optional | |

### Two independent axes, not one

POS-side openness (the role's default permission tier) and backend/portal access are **separate gates**,
matching the existing split between `access_profile` (POS-side tier) and `backend_role` (portal-side
gate) per grant:

- A role's *POS access default* (full/limited/fixed) maps to the POS-side permission tier.
- A role's *backend access default* (on/off, disable-able or grantable) maps to `backend_role` on a grant.

**Open item:** today's 4 system `access_profiles` (Manager, Supervisor, Cashier, Kitchen) don't line up
1:1 with the 5 target roles (Master User, Admin, Reporting Only, Manager, Staff) — see §5.

### Site assignment

A User has one **default site** (UI-level concept) but is stored once at the Group level and can hold
grants across multiple sites, each with its own role/access level (Admin/Manager/Staff per grant). This
matches the existing `user_access_grants` scope model exactly — only the role *names* and their default
permission sets are new.

---

## 3. Multi-identity login disambiguation

**Target:** logging in with an email associated with more than one identity (e.g. a SuperAdmin account
and a User-Master account sharing an email, or a User with grants across multiple roles) presents a
selection screen — the person picks which platform/role/scope to enter, then lands in the matching
portal/page.

**Already built (within the User/grant world):** the unified portal login flow already returns
`available_grants` when a User has multiple backend-role grants, and a follow-up call
(`/auth/portal/management-token`) finalizes the selection.

**Not yet built:** disambiguation *across* SuperAdmin and User identities sharing the same email.
SuperAdmin login and User login are currently fully separate flows with no shared lookup step.

---

## 4. Page-category permission hierarchy (new — not yet built)

Default page categories (open-ended list, designed for future expansion — not a fixed enum):

- Product & Menus
- App Configuration
- Reports
- User Management
- Customers & Loyalty

**Hierarchy rule:** a tab is visible only if the user has at least one granted permission within that
category. Specific pages/actions inside a visible tab are individually gated by their own permission.

**Licensing gate (orthogonal to role permissions):** some categories or pages are hidden entirely based
on the Brand/Site's license plan, regardless of role. This is a second, independent gate —
`visible = has_role_permission AND license_allows`, not folded into the role model itself.

---

## 5. Open questions / follow-ups

1. **Reseller Staff boundaries** — the user defined "Admin" as full SuperAdmin access but didn't specify
   what Reseller Staff is restricted from. Needs clarification before schema/permission work starts.
2. **System access profiles vs target roles** — decide whether the 4 existing system `access_profiles`
   (Manager/Supervisor/Cashier/Kitchen) are renamed/reduced to match the 5 target User roles, or whether
   `access_profiles` remains a separate, finer-grained tier layered underneath the 5 fixed roles.
3. **Per-category permission list** — only the 5 category names are fixed by this doc; the concrete
   permissions/pages inside each category are "to be expanded" per the original request.
