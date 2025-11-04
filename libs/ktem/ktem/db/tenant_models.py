import datetime
import uuid
from enum import Enum
from typing import Optional, List

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel, Relationship
from tzlocal import get_localzone


class UserRole(str, Enum):
    """User roles within a tenant"""
    SUPER_ADMIN = "super_admin" 
    ADMIN = "admin"
    USER = "user"


class TenantStatus(str, Enum):
    """Tenant status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class BaseTenant(SQLModel):
    """Base tenant model for multi-tenancy
    
    Attributes:
        id: canonical id to identify the tenant
        name: human-friendly name of the tenant
        domain: optional domain for the tenant
        status: status of the tenant (active, suspended, inactive)
        settings: tenant-specific settings
        date_created: the date the tenant was created
        date_updated: the date the tenant was updated
    """
    
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True
    )
    name: str = Field(min_length=1, max_length=255)
    domain: Optional[str] = Field(default=None, max_length=255, unique=True)
    status: TenantStatus = Field(default=TenantStatus.ACTIVE)
    settings: dict = Field(default={}, sa_column=Column(JSON))
    
    date_created: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )
    date_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )


class BaseTenantUser(SQLModel):
    """Enhanced user model with tenant and role support
    
    Attributes:
        id: canonical id to identify the user
        username: the username of the user
        email: email address of the user
        password: the hashed password of the user
        tenant_id: the tenant this user belongs to
        role: role of the user within the tenant
        is_active: whether the user account is active
        last_login: last login timestamp
    """
    
    __table_args__ = (
        UniqueConstraint('username', 'tenant_id', name='unique_username_per_tenant'),
        UniqueConstraint('email', 'tenant_id', name='unique_email_per_tenant'),
        {"extend_existing": True}
    )
    
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True
    )
    username: str = Field(min_length=1, max_length=255)
    username_lower: str = Field(max_length=255, index=True)
    email: str = Field(max_length=255)
    password: str
    
    # Tenant relationship
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    
    # Role within tenant
    role: UserRole = Field(default=UserRole.USER)
    
    # User status
    is_active: bool = Field(default=True)
    
    # Audit fields
    last_login: Optional[datetime.datetime] = Field(default=None)
    date_created: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )
    date_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )
    
    # Legacy compatibility
    admin: bool = Field(default=False, description="Legacy admin field for backward compatibility")


class BaseTenantConversation(SQLModel):
    """Enhanced conversation model with tenant support
    
    Attributes:
        id: canonical id to identify the conversation
        name: human-friendly name of the conversation
        user_id: the user id who owns the conversation
        tenant_id: the tenant this conversation belongs to
        data_source: the data source of the conversation
        is_public: whether the conversation is public within the tenant
        date_created: the date the conversation was created
        date_updated: the date the conversation was updated
    """
    
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True
    )
    name: str = Field(
        default_factory=lambda: "Untitled - {}".format(
            datetime.datetime.now(get_localzone()).strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    
    # User and tenant relationships
    user_id: str = Field(foreign_key="tenantuser.id", index=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    
    is_public: bool = Field(default=False, description="Public within tenant")
    
    # contains messages + current files + chat_suggestions
    data_source: dict = Field(default={}, sa_column=Column(JSON))
    
    date_created: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )
    date_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )
    
    # Legacy compatibility
    user: str = Field(default="", description="Legacy user field for backward compatibility")


class BaseTenantSettings(SQLModel):
    """Enhanced settings model with tenant support
    
    Attributes:
        id: canonical id to identify the settings
        user_id: the user id these settings belong to
        tenant_id: the tenant these settings belong to
        setting: the user settings (in dict/json format)
        is_tenant_wide: whether these are tenant-wide settings
    """
    
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True
    )
    
    # User and tenant relationships
    user_id: Optional[str] = Field(default=None, foreign_key="tenantuser.id")
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    
    setting: dict = Field(default={}, sa_column=Column(JSON))
    is_tenant_wide: bool = Field(default=False, description="Tenant-wide vs user-specific settings")
    
    # Legacy compatibility
    user: str = Field(default="", description="Legacy user field for backward compatibility")


class TenantInvitation(SQLModel):
    """Tenant invitation model for inviting users to join a tenant
    
    Attributes:
        id: canonical id to identify the invitation
        email: email address of the invited user
        tenant_id: the tenant the user is invited to
        role: role the user will have in the tenant
        invited_by: user id who sent the invitation
        token: invitation token for security
        expires_at: expiration date of the invitation
        accepted_at: date when invitation was accepted
        is_used: whether the invitation has been used
    """
    
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True
    )
    email: str = Field(max_length=255, index=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    role: UserRole = Field(default=UserRole.USER)
    invited_by: str = Field(foreign_key="tenantuser.id")
    
    token: str = Field(
        default_factory=lambda: uuid.uuid4().hex, unique=True, index=True
    )
    
    expires_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone()) + datetime.timedelta(days=7)
    )
    accepted_at: Optional[datetime.datetime] = Field(default=None)
    is_used: bool = Field(default=False)
    
    date_created: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(get_localzone())
    )
