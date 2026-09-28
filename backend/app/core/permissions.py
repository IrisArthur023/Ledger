from enum import Enum
from typing import Set, Dict


class Role(str, Enum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    EMPLOYEE = "EMPLOYEE"


class Permission(str, Enum):
    # User & Membership Management
    USER_MANAGE = "user:manage"
    ROLE_ASSIGN = "role:assign"
    
    # Business Configuration
    BUSINESS_CONFIGURE = "business:configure"
    
    # Account Management
    ACCOUNT_MANAGE = "account:manage"
    ACCOUNT_VIEW = "account:view"
    ACCOUNT_VIEW_BALANCE = "account:view_balance"
    
    # Category Management
    CATEGORY_MANAGE = "category:manage"
    CATEGORY_VIEW = "category:view"
    
    # Transactions
    TRANSACTION_CREATE = "transaction:create"
    TRANSACTION_VIEW_OWN = "transaction:view_own"
    TRANSACTION_VIEW_ALL = "transaction:view_all"
    TRANSACTION_EDIT_OWN = "transaction:edit_own"
    TRANSACTION_EDIT_ALL = "transaction:edit_all"
    TRANSACTION_VOID_OWN = "transaction:void_own"
    TRANSACTION_VOID_ALL = "transaction:void_all"
    
    # Reconciliation
    RECONCILIATION_VIEW = "reconciliation:view"
    RECONCILIATION_RESOLVE = "reconciliation:resolve"
    RECONCILIATION_RESOLVE_ASSIGNED = "reconciliation:resolve_assigned"
    
    # Reports
    REPORT_VIEW_BASIC = "report:view_basic"
    REPORT_VIEW_FULL = "report:view_full"
    REPORT_VIEW_ASSIGNED = "report:view_assigned"
    
    # AI Intelligence
    AI_CLASSIFY = "ai:classify"
    AI_FORECAST = "ai:forecast"
    AI_ANOMALIES = "ai:anomalies"


# Map roles to permissions explicitly
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.OWNER: {
        Permission.USER_MANAGE,
        Permission.ROLE_ASSIGN,
        Permission.BUSINESS_CONFIGURE,
        Permission.ACCOUNT_MANAGE,
        Permission.ACCOUNT_VIEW,
        Permission.ACCOUNT_VIEW_BALANCE,
        Permission.CATEGORY_MANAGE,
        Permission.CATEGORY_VIEW,
        Permission.TRANSACTION_CREATE,
        Permission.TRANSACTION_VIEW_OWN,
        Permission.TRANSACTION_VIEW_ALL,
        Permission.TRANSACTION_EDIT_OWN,
        Permission.TRANSACTION_EDIT_ALL,
        Permission.TRANSACTION_VOID_OWN,
        Permission.TRANSACTION_VOID_ALL,
        Permission.RECONCILIATION_VIEW,
        Permission.RECONCILIATION_RESOLVE,
        Permission.REPORT_VIEW_BASIC,
        Permission.REPORT_VIEW_FULL,
        Permission.AI_CLASSIFY,
        Permission.AI_FORECAST,
        Permission.AI_ANOMALIES,
    },
    Role.MANAGER: {
        Permission.ACCOUNT_VIEW,
        Permission.ACCOUNT_VIEW_BALANCE,
        Permission.CATEGORY_VIEW,
        Permission.TRANSACTION_CREATE,
        Permission.TRANSACTION_VIEW_OWN,
        Permission.TRANSACTION_VIEW_ALL,
        Permission.TRANSACTION_EDIT_OWN,
        Permission.RECONCILIATION_VIEW,
        Permission.RECONCILIATION_RESOLVE_ASSIGNED,
        Permission.REPORT_VIEW_BASIC,
        Permission.REPORT_VIEW_ASSIGNED,
        Permission.AI_CLASSIFY,
    },
    Role.EMPLOYEE: {
        Permission.ACCOUNT_VIEW,
        Permission.ACCOUNT_VIEW_BALANCE,
        Permission.CATEGORY_VIEW,
        Permission.TRANSACTION_CREATE,
        Permission.TRANSACTION_VIEW_OWN,
        Permission.TRANSACTION_EDIT_OWN,  # Employee can edit their own active transactions if permitted by policy
        Permission.AI_CLASSIFY,
    },
}


def has_permission(role: str, permission: Permission) -> bool:
    try:
        r = Role(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(r, set())
