from app.models.enums import StrEnum


class Permission(StrEnum):
    CONDOMINIUM_READ = "condominium.read"
    CONDOMINIUM_UPDATE = "condominium.update"
    UNITS_READ = "units.read"
    UNITS_MANAGE = "units.manage"
    RESIDENTS_READ = "residents.read"
    RESIDENTS_MANAGE = "residents.manage"
    STAFF_READ = "staff.read"
    STAFF_MANAGE = "staff.manage"
    AUDIT_READ = "audit.read"
    TICKETS_READ = "tickets.read"
    TICKETS_MANAGE = "tickets.manage"
    VISITORS_READ = "visitors.read"
    VISITORS_VALIDATE = "visitors.validate"
    DOCUMENTS_MANAGE = "documents.manage"
    CONVERSATIONS_READ = "conversations.read"
    CONVERSATIONS_REPLY = "conversations.reply"


class Role(StrEnum):
    """Effective role of a user in one condominium."""

    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    MANAGER = "manager"
    STAFF = "staff"


_ALL = frozenset(Permission)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ORG_OWNER: _ALL,
    Role.ORG_ADMIN: _ALL,
    Role.MANAGER: _ALL,
    # Front desk: verify visitors, see units and tickets. No resident directory access.
    Role.STAFF: frozenset(
        {
            Permission.CONDOMINIUM_READ,
            Permission.UNITS_READ,
            Permission.TICKETS_READ,
            Permission.VISITORS_READ,
            Permission.VISITORS_VALIDATE,
        }
    ),
}

ORG_LEVEL_ROLES = frozenset({Role.ORG_OWNER, Role.ORG_ADMIN})
