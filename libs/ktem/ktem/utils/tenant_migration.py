"""
Utility for migrating existing single-tenant data to multi-tenant structure
"""

import datetime
from typing import List, Dict, Any, Optional

from sqlmodel import Session, select
from ktem.db.models import (
    User, Conversation, Settings, 
    Tenant, TenantUser, TenantConversation, TenantSettings,
    engine
)
from ktem.db.tenant_models import UserRole, TenantStatus
from ktem.services.tenant_auth import TenantAuthService


class TenantMigrationService:
    """Service for migrating existing data to multi-tenant structure"""
    
    @staticmethod
    def migrate_to_tenant_system(
        default_tenant_name: str = "Default Organization",
        default_tenant_domain: Optional[str] = None,
        make_first_user_admin: bool = True
    ) -> Dict[str, Any]:
        """
        Migrate existing single-tenant data to multi-tenant structure
        
        Args:
            default_tenant_name: Name for the default tenant
            default_tenant_domain: Domain for the default tenant
            make_first_user_admin: Whether to make the first user an admin
            
        Returns:
            Migration report
        """
        with Session(engine) as session:
            # Check if migration is needed
            existing_tenants = session.exec(select(Tenant)).all()
            if existing_tenants:
                return {
                    "status": "skipped",
                    "message": "Tenants already exist, migration not needed"
                }
            
            # Create default tenant
            default_tenant = Tenant(
                name=default_tenant_name,
                domain=default_tenant_domain,
                status=TenantStatus.ACTIVE,
                settings={}
            )
            session.add(default_tenant)
            session.flush()  # Get tenant ID
            
            # Migrate users
            existing_users = session.exec(select(User)).all()
            migrated_users = []
            
            for i, old_user in enumerate(existing_users):
                # Determine role (first user or existing admin becomes admin)
                is_admin = (i == 0 and make_first_user_admin) or old_user.admin
                role = UserRole.ADMIN if is_admin else UserRole.USER
                
                # Create tenant user
                tenant_user = TenantUser(
                    id=old_user.id,  # Keep same ID for compatibility
                    username=old_user.username,
                    username_lower=old_user.username_lower,
                    email=old_user.username,  # Use username as email if no email field
                    password=old_user.password,
                    tenant_id=default_tenant.id,
                    role=role,
                    is_active=True,
                    admin=old_user.admin,  # Keep for compatibility
                    date_created=datetime.datetime.now(),
                    date_updated=datetime.datetime.now()
                )
                
                session.add(tenant_user)
                migrated_users.append({
                    "old_id": old_user.id,
                    "new_id": tenant_user.id,
                    "username": old_user.username,
                    "role": role.value
                })
            
            # Migrate conversations
            existing_conversations = session.exec(select(Conversation)).all()
            migrated_conversations = []
            
            for old_conv in existing_conversations:
                # Find corresponding tenant user
                user_id = old_conv.user or None  # Handle legacy user field
                
                tenant_conv = TenantConversation(
                    id=old_conv.id,  # Keep same ID
                    name=old_conv.name,
                    user_id=user_id,
                    tenant_id=default_tenant.id,
                    is_public=old_conv.is_public,
                    data_source=old_conv.data_source,
                    date_created=old_conv.date_created,
                    date_updated=old_conv.date_updated,
                    user=old_conv.user  # Keep legacy field
                )
                
                session.add(tenant_conv)
                migrated_conversations.append({
                    "id": old_conv.id,
                    "name": old_conv.name,
                    "user_id": user_id
                })
            
            # Migrate settings
            existing_settings = session.exec(select(Settings)).all()
            migrated_settings = []
            
            for old_setting in existing_settings:
                user_id = old_setting.user or None
                
                tenant_setting = TenantSettings(
                    id=old_setting.id,  # Keep same ID
                    user_id=user_id,
                    tenant_id=default_tenant.id,
                    setting=old_setting.setting,
                    is_tenant_wide=(user_id is None),
                    user=old_setting.user  # Keep legacy field
                )
                
                session.add(tenant_setting)
                migrated_settings.append({
                    "id": old_setting.id,
                    "user_id": user_id,
                    "is_tenant_wide": user_id is None
                })
            
            # Commit all changes
            session.commit()
            
            return {
                "status": "success",
                "tenant": {
                    "id": default_tenant.id,
                    "name": default_tenant.name,
                    "domain": default_tenant.domain
                },
                "migrated": {
                    "users": len(migrated_users),
                    "conversations": len(migrated_conversations), 
                    "settings": len(migrated_settings)
                },
                "details": {
                    "users": migrated_users,
                    "conversations": migrated_conversations,
                    "settings": migrated_settings
                }
            }
    
    @staticmethod
    def create_migration_backup() -> Dict[str, Any]:
        """
        Create a backup of existing data before migration
        
        Returns:
            Backup data
        """
        with Session(engine) as session:
            backup = {
                "users": [],
                "conversations": [],
                "settings": [],
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # Backup users
            users = session.exec(select(User)).all()
            for user in users:
                backup["users"].append({
                    "id": user.id,
                    "username": user.username,
                    "username_lower": user.username_lower,
                    "password": user.password,
                    "admin": user.admin
                })
            
            # Backup conversations
            conversations = session.exec(select(Conversation)).all()
            for conv in conversations:
                backup["conversations"].append({
                    "id": conv.id,
                    "name": conv.name,
                    "user": conv.user,
                    "is_public": conv.is_public,
                    "data_source": conv.data_source,
                    "date_created": conv.date_created.isoformat(),
                    "date_updated": conv.date_updated.isoformat()
                })
            
            # Backup settings
            settings = session.exec(select(Settings)).all()
            for setting in settings:
                backup["settings"].append({
                    "id": setting.id,
                    "user": setting.user,
                    "setting": setting.setting
                })
            
            return backup
    
    @staticmethod
    def verify_migration() -> Dict[str, Any]:
        """
        Verify migration was successful
        
        Returns:
            Verification report
        """
        with Session(engine) as session:
            # Count original records
            original_users = len(list(session.exec(select(User)).all()))
            original_conversations = len(list(session.exec(select(Conversation)).all()))
            original_settings = len(list(session.exec(select(Settings)).all()))
            
            # Count migrated records
            tenants = len(list(session.exec(select(Tenant)).all()))
            tenant_users = len(list(session.exec(select(TenantUser)).all()))
            tenant_conversations = len(list(session.exec(select(TenantConversation)).all()))
            tenant_settings = len(list(session.exec(select(TenantSettings)).all()))
            
            return {
                "tenants_created": tenants,
                "migration_complete": tenants > 0,
                "data_integrity": {
                    "users": {
                        "original": original_users,
                        "migrated": tenant_users,
                        "match": original_users == tenant_users
                    },
                    "conversations": {
                        "original": original_conversations,
                        "migrated": tenant_conversations,
                        "match": original_conversations == tenant_conversations
                    },
                    "settings": {
                        "original": original_settings,
                        "migrated": tenant_settings,
                        "match": original_settings == tenant_settings
                    }
                }
            }
    
    @staticmethod
    def get_migration_status() -> Dict[str, Any]:
        """
        Check current migration status
        
        Returns:
            Current status information
        """
        with Session(engine) as session:
            # Check if we have tenants (migration done)
            tenants = session.exec(select(Tenant)).all()
            tenant_users = session.exec(select(TenantUser)).all()
            
            # Check if we have legacy data
            legacy_users = session.exec(select(User)).all()
            
            if tenants:
                status = "migrated"
                message = f"Migration complete. {len(tenants)} tenant(s), {len(tenant_users)} user(s)"
            elif legacy_users:
                status = "needs_migration"
                message = f"Migration needed. {len(legacy_users)} legacy user(s) found"
            else:
                status = "fresh_install"
                message = "Fresh installation. No data to migrate"
            
            return {
                "status": status,
                "message": message,
                "counts": {
                    "tenants": len(tenants),
                    "tenant_users": len(tenant_users),
                    "legacy_users": len(legacy_users)
                }
            }


def run_migration_if_needed(
    tenant_name: Optional[str] = None,
    tenant_domain: Optional[str] = None,
    admin_username: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None
) -> bool:
    """
    Run migration if needed
    
    Args:
        tenant_name: Name for default tenant (uses config default if None)
        tenant_domain: Domain for default tenant (uses config default if None)
        admin_username: Admin username (uses config default if None)
        admin_email: Admin email (uses config default if None)
        admin_password: Admin password (uses config default if None)
        
    Returns:
        True if migration was run, False if not needed
    """
    # Load defaults from settings if not provided
    if tenant_name is None:
        from theflow.settings import settings as flowsettings
        tenant_name = getattr(flowsettings, "KH_DEFAULT_TENANT_NAME", "Default Organization")
    
    if tenant_domain is None:
        from theflow.settings import settings as flowsettings
        tenant_domain = getattr(flowsettings, "KH_DEFAULT_TENANT_DOMAIN", None)
    
    if admin_username is None:
        from theflow.settings import settings as flowsettings
        admin_username = getattr(flowsettings, "KH_DEFAULT_SUPER_ADMIN", "superadmin")
    
    if admin_email is None:
        from theflow.settings import settings as flowsettings
        admin_email = getattr(flowsettings, "KH_DEFAULT_SUPER_ADMIN_EMAIL", "superadmin@kotaemon.com")
    
    if admin_password is None:
        from theflow.settings import settings as flowsettings
        admin_password = getattr(flowsettings, "KH_DEFAULT_SUPER_ADMIN_PASSWORD", "superadmin")
    
    status = TenantMigrationService.get_migration_status()
    
    if status["status"] == "needs_migration":
        print("🔄 Running tenant migration...")
        print(f"📋 Using defaults: Tenant='{tenant_name}', Admin='{admin_username}', Email='{admin_email}'")
        
        # Create backup
        print("📦 Creating backup...")
        backup = TenantMigrationService.create_migration_backup()
        print(f"📦 Backup created with {len(backup['users'])} users, "
              f"{len(backup['conversations'])} conversations, "
              f"{len(backup['settings'])} settings")
        
        # Run migration
        print("🚀 Migrating to tenant system...")
        result = TenantMigrationService.migrate_to_tenant_system(
            default_tenant_name=tenant_name,
            default_tenant_domain=tenant_domain
        )
        
        if result["status"] == "success":
            print("✅ Migration completed successfully!")
            print(f"📊 Migrated: {result['migrated']['users']} users, "
                  f"{result['migrated']['conversations']} conversations, "
                  f"{result['migrated']['settings']} settings")
            
            # Verify migration
            verification = TenantMigrationService.verify_migration()
            if verification["migration_complete"]:
                print("✅ Migration verification passed!")
                return True
            else:
                print("❌ Migration verification failed!")
                return False
        else:
            print(f"❌ Migration failed: {result.get('message', 'Unknown error')}")
            return False
    
    elif status["status"] == "migrated":
        print("ℹ️  Migration already completed")
        return False
    
    elif status["status"] == "fresh_install":
        print("🆕 Fresh installation detected, creating default tenant...")
        print(f"📋 Using defaults: Tenant='{tenant_name}', Admin='{admin_username}', Email='{admin_email}'")
        
        try:
            tenant, admin_user = TenantAuthService.create_tenant(
                name=tenant_name,
                domain=tenant_domain,
                admin_username=admin_username,
                admin_email=admin_email,
                admin_password=admin_password
            )
            
            print(f"✅ Default tenant '{tenant.name}' created successfully!")
            print(f"👤 Admin user '{admin_user.username}' created with role: {admin_user.role.value}")
            print(f"🔑 Default login: username='{admin_username}', password='{admin_password}'")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to create default tenant: {e}")
            return False
    
    else:
        print("ℹ️  No migration needed")
        return False


def ensure_default_tenant() -> bool:
    """
    Ensure a default tenant exists, similar to how default users are created.
    This function can be called at app startup to guarantee a tenant exists.
    
    Returns:
        True if tenant was created, False if already exists
    """
    from theflow.settings import settings as flowsettings
    
    # Get settings
    tenant_name = getattr(flowsettings, "KH_DEFAULT_TENANT_NAME", "Default Organization")
    tenant_domain = getattr(flowsettings, "KH_DEFAULT_TENANT_DOMAIN", None)
    
    # Super Admin credentials
    super_admin_username = getattr(flowsettings, "KH_DEFAULT_SUPER_ADMIN", "superadmin")
    super_admin_email = getattr(flowsettings, "KH_DEFAULT_SUPER_ADMIN_EMAIL", "superadmin@kotaemon.com")
    super_admin_password = getattr(flowsettings, "KH_DEFAULT_SUPER_ADMIN_PASSWORD", "superadmin")
    
    # Admin credentials
    admin_username = getattr(flowsettings, "KH_DEFAULT_TENANT_ADMIN", "admin")
    admin_email = getattr(flowsettings, "KH_DEFAULT_TENANT_ADMIN_EMAIL", "admin@kotaemon.com")
    admin_password = getattr(flowsettings, "KH_DEFAULT_TENANT_ADMIN_PASSWORD", "admin")
    
    # User credentials
    user_username = getattr(flowsettings, "KH_DEFAULT_USER", "user")
    user_email = getattr(flowsettings, "KH_DEFAULT_USER_EMAIL", "user@kotaemon.com")
    user_password = getattr(flowsettings, "KH_DEFAULT_USER_PASSWORD", "user")
    
    with Session(engine) as session:
        # Check if any tenants exist
        existing_tenants = session.exec(select(Tenant)).all()
        
        if existing_tenants:
            # Tenants exist, check if default admin user exists in any tenant
            existing_admin = session.exec(
                select(TenantUser).where(
                    TenantUser.username_lower == admin_username.lower(),
                    TenantUser.role == UserRole.ADMIN
                )
            ).first()
            
            if existing_admin:
                print(f"ℹ️  Default tenant admin '{admin_username}' already exists")
                return False
            else:
                print(f"⚠️  Tenants exist but no admin user '{admin_username}' found")
                return False
        
        # No tenants exist, create default tenant with all three user roles
        print(f"🏗️  Creating default tenant '{tenant_name}' with three user roles...")
        
        try:
            # Create tenant with super admin first
            tenant, super_admin_user = TenantAuthService.create_tenant(
                name=tenant_name,
                domain=tenant_domain,
                admin_username=super_admin_username,
                admin_email=super_admin_email,
                admin_password=super_admin_password
            )
            
            # Update super admin role to SUPER_ADMIN and create other users
            with Session(engine) as session:
                # Update super admin role
                super_admin_user_db = session.get(TenantUser, super_admin_user.id)
                super_admin_user_db.role = UserRole.SUPER_ADMIN
                session.add(super_admin_user_db)
                
                # Create regular admin user
                admin_user_db = TenantUser(
                    username=admin_username,
                    username_lower=admin_username.lower(),
                    email=admin_email,
                    password=TenantAuthService.hash_password(admin_password),
                    tenant_id=tenant.id,
                    role=UserRole.ADMIN,
                    is_active=True
                )
                session.add(admin_user_db)
                
                # Create regular user
                regular_user_db = TenantUser(
                    username=user_username,
                    username_lower=user_username.lower(),
                    email=user_email,
                    password=TenantAuthService.hash_password(user_password),
                    tenant_id=tenant.id,
                    role=UserRole.USER,
                    is_active=True
                )
                session.add(regular_user_db)
                
                session.commit()
            
            print(f"✅ Default tenant created successfully!")
            print(f"🏢 Tenant: {tenant.name} (ID: {tenant.id})")
            print()
            print(f"👑 SUPER ADMIN (full access + tenant management):")
            print(f"   Username: {super_admin_username}")
            print(f"   Password: {super_admin_password}")
            print(f"   Email: {super_admin_email}")
            print()
            print(f"🛡️  ADMIN (chat, files, resources, settings, help):")
            print(f"   Username: {admin_username}")
            print(f"   Password: {admin_password}")
            print(f"   Email: {admin_email}")
            print()
            print(f"👤 USER (chat and files only):")
            print(f"   Username: {user_username}")
            print(f"   Password: {user_password}")
            print(f"   Email: {user_email}")
            print()
            print(f"🌐 Access at: http://localhost:7860 (or your configured URL)")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to create default tenant: {e}")
            return False
