import ktem.db.base_models as base_models
import ktem.db.tenant_models as tenant_models
from ktem.db.engine import engine
from sqlmodel import SQLModel
from theflow.settings import settings
from theflow.utils.modules import import_dotted_string

_base_conv = (
    import_dotted_string(settings.KH_TABLE_CONV, safe=False)
    if hasattr(settings, "KH_TABLE_CONV")
    else base_models.BaseConversation
)

_base_user = (
    import_dotted_string(settings.KH_TABLE_USER, safe=False)
    if hasattr(settings, "KH_TABLE_USER")
    else base_models.BaseUser
)

_base_settings = (
    import_dotted_string(settings.KH_TABLE_SETTINGS, safe=False)
    if hasattr(settings, "KH_TABLE_SETTINGS")
    else base_models.BaseSettings
)

_base_issue_report = (
    import_dotted_string(settings.KH_TABLE_ISSUE_REPORT, safe=False)
    if hasattr(settings, "KH_TABLE_ISSUE_REPORT")
    else base_models.BaseIssueReport
)


class Conversation(_base_conv, table=True):  # type: ignore
    """Conversation record"""


class User(_base_user, table=True):  # type: ignore
    """User table"""


class Settings(_base_settings, table=True):  # type: ignore
    """Record of settings"""


class IssueReport(_base_issue_report, table=True):  # type: ignore
    """Record of issues"""


# Tenant-aware models
class Tenant(tenant_models.BaseTenant, table=True):  # type: ignore
    """Tenant table for multi-tenancy"""


class TenantUser(tenant_models.BaseTenantUser, table=True):  # type: ignore
    """Enhanced user table with tenant support"""


class TenantConversation(tenant_models.BaseTenantConversation, table=True):  # type: ignore
    """Enhanced conversation table with tenant support"""


class TenantSettings(tenant_models.BaseTenantSettings, table=True):  # type: ignore
    """Enhanced settings table with tenant support"""


class TenantInvitation(tenant_models.TenantInvitation, table=True):  # type: ignore
    """Tenant invitation table"""


if not getattr(settings, "KH_ENABLE_ALEMBIC", False):
    SQLModel.metadata.create_all(engine)
