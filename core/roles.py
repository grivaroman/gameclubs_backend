ROLE_USER = "user"
ROLE_PENDING_OWNER = "pending_owner"
ROLE_ADMIN = "admin"
ROLE_OWNER = "owner"
ROLE_SUPERADMIN = "superadmin"

PLAYER_ROLES = {ROLE_USER}
CLUB_ADMIN_ROLES = {ROLE_ADMIN, ROLE_OWNER}
STAFF_ROLES = CLUB_ADMIN_ROLES | {ROLE_SUPERADMIN}
ALL_ROLES = PLAYER_ROLES | {ROLE_PENDING_OWNER} | STAFF_ROLES


def is_valid_role(role: str | None) -> bool:
    return role in ALL_ROLES


def can_manage_clubs(role: str | None) -> bool:
    return role in CLUB_ADMIN_ROLES
