"""Role -> permission table. The backend enforces these on every mutation;
the frontend only uses them (via /api/auth/me) to decide which buttons to
show. Deterministic -- no AI involved in authorization.

Sign-up makes the user the ``owner`` of their own tenant. The other roles
exist so tenants with several members can be added without touching any
endpoint: each endpoint asks for a permission, never a role.
"""

from enum import StrEnum


class Permission(StrEnum):
    VIEW = "view"
    UPLOAD = "workbooks:upload"
    EDIT_WORKBOOK = "workbooks:edit"
    CREATE_RECORD = "records:create"
    EDIT_RECORD = "records:edit"
    DELETE_RECORD = "records:delete"
    DECIDE = "records:approve"  # approve / reject in an approval workflow


_ALL = frozenset(Permission)

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": _ALL,
    "admin": _ALL,
    "approver": frozenset({Permission.VIEW, Permission.DECIDE}),
    "editor": frozenset(
        {Permission.VIEW, Permission.UPLOAD, Permission.CREATE_RECORD, Permission.EDIT_RECORD, Permission.DELETE_RECORD}
    ),
    "viewer": frozenset({Permission.VIEW}),
}


def permissions_for(role: str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for(role)
