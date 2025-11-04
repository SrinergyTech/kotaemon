import hashlib
import datetime
import json
import uuid
import os
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select
from ktem.db.models import Tenant, TenantUser, TenantInvitation, engine
from ktem.db.tenant_models import UserRole, TenantStatus
from tzlocal import get_localzone


@dataclass
class AuthUser:
    """Authenticated user context"""
    id: str
    username: str
    email: str
    tenant_id: str
    tenant_name: str
    role: UserRole
    is_active: bool
    session_id: Optional[str] = None
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin privileges"""
        return self.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
    
    @property
    def is_super_admin(self) -> bool:
        """Check if user has super admin privileges"""
        return self.role == UserRole.SUPER_ADMIN
    
    @property
    def can_manage_users(self) -> bool:
        """Check if user can manage other users in tenant"""
        return self.is_admin
    
    @property
    def can_manage_tenant(self) -> bool:
        """Check if user can manage tenant settings"""
        return self.is_admin


class TenantAuthService:
    """Tenant authentication and authorization service"""
    
    # Session management
    _sessions_dir = Path(".kotaemon_sessions")
    _session_timeout_hours = 24
    
    @classmethod
    def _ensure_sessions_dir(cls):
        """Ensure sessions directory exists"""
        cls._sessions_dir.mkdir(exist_ok=True)
    
    @classmethod
    def _get_session_file(cls, session_id: str) -> Path:
        """Get session file path"""
        return cls._sessions_dir / f"{session_id}.json"
    
    @classmethod
    def _cleanup_expired_sessions(cls):
        """Clean up expired session files"""
        if not cls._sessions_dir.exists():
            return
        
        current_time = datetime.datetime.now()
        
        for session_file in cls._sessions_dir.glob("*.json"):
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                
                expires_at = datetime.datetime.fromisoformat(session_data['expires_at'])
                if current_time > expires_at:
                    session_file.unlink()
                    
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                # Invalid file, delete it
                try:
                    session_file.unlink()
                except OSError:
                    pass
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return TenantAuthService.hash_password(password) == hashed
    
    @classmethod
    def authenticate_user(cls, username: str, password: str, tenant_domain: Optional[str] = None) -> Optional[AuthUser]:
        """
        Authenticate user with tenant support
        
        Args:
            username: Username or email
            password: Plain text password
            tenant_domain: Optional tenant domain for domain-based routing
            
        Returns:
            AuthUser object if authentication successful, None otherwise
        """
        with Session(engine) as session:
            # Build query for user lookup
            query = select(TenantUser, Tenant).join(Tenant, TenantUser.tenant_id == Tenant.id)
            
            # Add username/email filter
            query = query.where(
                (TenantUser.username_lower == username.lower().strip()) |
                (TenantUser.email == username.lower().strip())
            )
            
            # Add tenant domain filter if provided
            if tenant_domain:
                query = query.where(Tenant.domain == tenant_domain)
            
            # Only active users and tenants
            query = query.where(
                TenantUser.is_active == True,
                Tenant.status == TenantStatus.ACTIVE
            )
            
            result = session.exec(query).first()
            
            if not result:
                return None
                
            user, tenant = result
            
            # Verify password
            if not cls.verify_password(password, user.password):
                return None
            
            # Update last login
            user.last_login = datetime.datetime.now(get_localzone())
            session.add(user)
            session.commit()
            
            auth_user = AuthUser(
                id=user.id,
                username=user.username,
                email=user.email,
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                role=user.role,
                is_active=user.is_active
            )
            
            # Create session for authenticated user
            session_id = cls.create_session(auth_user)
            
            # Store session ID in auth_user for retrieval
            auth_user.session_id = session_id
            
            return auth_user
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[AuthUser]:
        """Get authenticated user by ID"""
        with Session(engine) as session:
            query = select(TenantUser, Tenant).join(Tenant, TenantUser.tenant_id == Tenant.id)
            query = query.where(
                TenantUser.id == user_id,
                TenantUser.is_active == True,
                Tenant.status == TenantStatus.ACTIVE
            )
            
            result = session.exec(query).first()
            if not result:
                return None
                
            user, tenant = result
            
            return AuthUser(
                id=user.id,
                username=user.username,
                email=user.email,
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                role=user.role,
                is_active=user.is_active
            )
    
    @staticmethod
    def create_tenant(name: str, domain: Optional[str] = None, admin_username: str = None, 
                     admin_email: str = None, admin_password: str = None) -> Tuple[Tenant, TenantUser]:
        """
        Create a new tenant with admin user
        
        Args:
            name: Tenant name
            domain: Optional tenant domain
            admin_username: Admin username
            admin_email: Admin email
            admin_password: Admin password (plain text)
            
        Returns:
            Tuple of (Tenant, TenantUser)
        """
        with Session(engine) as session:
            # Create tenant
            tenant = Tenant(
                name=name,
                domain=domain,
                status=TenantStatus.ACTIVE
            )
            session.add(tenant)
            session.flush()  # Get tenant ID
            
            # Create admin user
            admin_user = TenantUser(
                username=admin_username,
                username_lower=admin_username.lower(),
                email=admin_email,
                password=TenantAuthService.hash_password(admin_password),
                tenant_id=tenant.id,
                role=UserRole.ADMIN,
                is_active=True,
                admin=True  # For legacy compatibility
            )
            session.add(admin_user)
            session.commit()
            
            return tenant, admin_user
    
    @staticmethod
    def create_user(tenant_id: str, username: str, email: str, password: str, 
                   role: UserRole = UserRole.USER, created_by: str = None) -> TenantUser:
        """
        Create a new user in a tenant
        
        Args:
            tenant_id: Tenant ID
            username: Username
            email: Email address
            password: Plain text password
            role: User role
            created_by: ID of user creating this user (for audit)
            
        Returns:
            Created TenantUser
        """
        with Session(engine) as session:
            user = TenantUser(
                username=username,
                username_lower=username.lower(),
                email=email,
                password=TenantAuthService.hash_password(password),
                tenant_id=tenant_id,
                role=role,
                is_active=True,
                admin=(role == UserRole.ADMIN)  # For legacy compatibility
            )
            session.add(user)
            session.commit()
            
            return user
    
    @staticmethod
    def invite_user(tenant_id: str, email: str, role: UserRole, invited_by: str) -> TenantInvitation:
        """
        Create an invitation for a user to join a tenant
        
        Args:
            tenant_id: Tenant ID
            email: Email to invite
            role: Role for the user
            invited_by: ID of user sending invitation
            
        Returns:
            TenantInvitation object
        """
        with Session(engine) as session:
            invitation = TenantInvitation(
                email=email,
                tenant_id=tenant_id,
                role=role,
                invited_by=invited_by
            )
            session.add(invitation)
            session.commit()
            
            return invitation
    
    @staticmethod
    def accept_invitation(token: str, username: str, password: str) -> Optional[TenantUser]:
        """
        Accept a tenant invitation and create user account
        
        Args:
            token: Invitation token
            username: Desired username
            password: Plain text password
            
        Returns:
            Created TenantUser if successful, None otherwise
        """
        with Session(engine) as session:
            # Find valid invitation
            invitation = session.exec(
                select(TenantInvitation).where(
                    TenantInvitation.token == token,
                    TenantInvitation.is_used == False,
                    TenantInvitation.expires_at > datetime.datetime.now(get_localzone())
                )
            ).first()
            
            if not invitation:
                return None
            
            # Check if user already exists in tenant
            existing_user = session.exec(
                select(TenantUser).where(
                    TenantUser.tenant_id == invitation.tenant_id,
                    (TenantUser.username_lower == username.lower()) | 
                    (TenantUser.email == invitation.email)
                )
            ).first()
            
            if existing_user:
                return None
            
            # Create user
            user = TenantUser(
                username=username,
                username_lower=username.lower(),
                email=invitation.email,
                password=TenantAuthService.hash_password(password),
                tenant_id=invitation.tenant_id,
                role=invitation.role,
                is_active=True,
                admin=(invitation.role == UserRole.ADMIN)  # For legacy compatibility
            )
            session.add(user)
            
            # Mark invitation as used
            invitation.is_used = True
            invitation.accepted_at = datetime.datetime.now(get_localzone())
            session.add(invitation)
            
            session.commit()
            return user
    
    @staticmethod
    def get_tenant_users(tenant_id: str, include_inactive: bool = False) -> list[TenantUser]:
        """Get all users in a tenant"""
        with Session(engine) as session:
            query = select(TenantUser).where(TenantUser.tenant_id == tenant_id)
            
            if not include_inactive:
                query = query.where(TenantUser.is_active == True)
            
            return list(session.exec(query).all())
    
    @staticmethod
    def update_user_role(user_id: str, new_role: UserRole, updated_by: str) -> Optional[TenantUser]:
        """Update user role within tenant"""
        with Session(engine) as session:
            user = session.get(TenantUser, user_id)
            if not user:
                return None
            
            user.role = new_role
            user.admin = (new_role == UserRole.ADMIN)  # Legacy compatibility
            user.date_updated = datetime.datetime.now(get_localzone())
            
            session.add(user)
            session.commit()
            
            return user
    
    @staticmethod
    def deactivate_user(user_id: str, deactivated_by: str) -> Optional[TenantUser]:
        """Deactivate a user account"""
        with Session(engine) as session:
            user = session.get(TenantUser, user_id)
            if not user:
                return None
            
            user.is_active = False
            user.date_updated = datetime.datetime.now(get_localzone())
            
            session.add(user)
            session.commit()
            
            return user
    
    @classmethod
    def create_session(cls, auth_user: AuthUser) -> str:
        """Create a new session for authenticated user"""
        cls._ensure_sessions_dir()
        cls._cleanup_expired_sessions()
        
        session_id = str(uuid.uuid4())
        session_data = {
            "session_id": session_id,
            "user_id": auth_user.id,
            "username": auth_user.username,
            "role": auth_user.role.value,
            "tenant_id": auth_user.tenant_id,
            "tenant_name": auth_user.tenant_name,
            "created_at": datetime.datetime.now().isoformat(),
            "expires_at": (datetime.datetime.now() + datetime.timedelta(hours=cls._session_timeout_hours)).isoformat()
        }
        
        session_file = cls._get_session_file(session_id)
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        return session_id
    
    @classmethod
    def get_session(cls, session_id: str) -> Optional[Dict]:
        """Get session data by session ID"""
        if not session_id:
            return None
        
        session_file = cls._get_session_file(session_id)
        if not session_file.exists():
            return None
        
        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            # Check if session is expired
            expires_at = datetime.datetime.fromisoformat(session_data['expires_at'])
            if datetime.datetime.now() > expires_at:
                cls._delete_session(session_id)
                return None
            
            return session_data
        except (json.JSONDecodeError, KeyError, ValueError):
            cls._delete_session(session_id)
            return None
    
    @classmethod
    def get_user_from_session(cls, session_id: str) -> Optional[str]:
        """Get user ID from session"""
        session_data = cls.get_session(session_id)
        return session_data['user_id'] if session_data else None
    
    @classmethod
    def delete_session(cls, session_id: str) -> bool:
        """Delete a session (logout)"""
        return cls._delete_session(session_id)
    
    @classmethod
    def _delete_session(cls, session_id: str) -> bool:
        """Internal method to delete a session file"""
        session_file = cls._get_session_file(session_id)
        if session_file.exists():
            try:
                session_file.unlink()
                return True
            except OSError:
                return False
        return False


class TenantAuthMiddleware:
    """Middleware for tenant-aware authorization"""
    
    @staticmethod
    def require_auth(user_context: Optional[AuthUser]) -> bool:
        """Check if user is authenticated"""
        return user_context is not None and user_context.is_active
    
    @staticmethod
    def require_admin(user_context: Optional[AuthUser]) -> bool:
        """Check if user is admin in their tenant"""
        return (TenantAuthMiddleware.require_auth(user_context) and 
                user_context.is_admin)
    
    @staticmethod
    def require_same_tenant(user_context: Optional[AuthUser], resource_tenant_id: str) -> bool:
        """Check if user belongs to the same tenant as resource"""
        return (TenantAuthMiddleware.require_auth(user_context) and 
                user_context.tenant_id == resource_tenant_id)
    
    @staticmethod
    def can_manage_user(actor: Optional[AuthUser], target_user_id: str) -> bool:
        """Check if actor can manage target user"""
        if not TenantAuthMiddleware.require_admin(actor):
            return False
        
        with Session(engine) as session:
            target_user = session.get(TenantUser, target_user_id)
            if not target_user:
                return False
            
            return actor.tenant_id == target_user.tenant_id
