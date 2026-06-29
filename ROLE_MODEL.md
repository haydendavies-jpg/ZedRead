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
| Admin | Full ZedRead administrative access — sees and manages all Groups across all resellers. |
| Reseller Staff | Partner-side staff. Scoped to **own accounts only**: can create/view/manage only the Groups they personally created or are assigned to. No visibility into other resellers' or ZedRead-direct accounts. |

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

### Required fields (Stage 15 slice 5 — enforced)

| Field | Rule | Status |
|---|---|---|
| First name, Last name | Required for every User except Master User (see below). | Enforced at creation (`UserCreate`, `InviteAcceptRequest`); columns nullable in the DB, mirroring the existing `is_master_user` exception pattern. |
| PIN | Required for every User except Master User. | Already satisfied by existing mechanics — `UserPIN` is set lazily, and `pos_auth_service` treats an absent PIN as `is_pin_reset_required=True`, so a User can never reach a state where POS PIN entry is silently skipped. No blocking creation-time check added (no PIN-primary login flow exists yet — Android app is Stage 13-14, out of scope here). |
| Email | Optional, **unless** the user has backend access granted — then required. | Enforced: setting `backend_role` on the `User` row (`routes/users.py update_user()`) or on a `UserAccessGrant` (`access_grant_service.update_grant()`) is rejected with 409 unless the user already has both email and password_hash set. |
| Backend password | Only required if a backend access permission is set on at least one grant. | Enforced via the same email+password_hash check above; `UserCreate` additionally rejects a half-supplied email/password pair (both or neither). |

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

**Decision:** the 4 existing system `access_profiles` (Manager, Supervisor, Cashier, Kitchen) are
**replaced** by the 5 target roles. `access_profiles` becomes exactly Master User / Admin /
Reporting Only / Manager / Staff — one tier, not two. No separate sub-tier underneath.

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
category. **Grain: per-page toggle within category** — each page inside a category (e.g. "Daily Sales"
vs "Tax Collected" under Reports) has its own independently grantable permission; the category tab is
shown if any page underneath it is granted. This is one level of granularity beyond a whole-category
toggle, but does not split further into per-action (view/edit/delete) permissions within a page —
"Reporting Only" achieves view-without-edit by being granted the page itself but not the products/menus
pages that have edit actions, not by an action-level flag.

**Licensing gate (orthogonal to role permissions):** some categories or pages are hidden entirely based
on the Brand/Site's license plan, regardless of role. This is a second, independent gate —
`visible = has_role_permission AND license_allows`, not folded into the role model itself.

---

## 5. Resolved decisions

1. **Reseller Staff boundaries** — own-accounts-only: Reseller Staff sees/manages only Groups they
   created or are assigned to. Admin sees everything. (See §1.)
2. **System access profiles vs target roles** — the 4 existing system profiles are replaced by the 5
   target roles; `access_profiles` is not a separate sub-tier. (See §2, "Two independent axes" note.)
3. **Permission grain per page category** — per-page toggle within each category, not whole-category-only
   and not per-action. (See §4.)

## 6. Still open / to be expanded

- The concrete list of pages within each category (e.g. exactly which pages live under Reports vs
  Customers & Loyalty) is not yet enumerated — to be defined when this work is scheduled into a stage.
