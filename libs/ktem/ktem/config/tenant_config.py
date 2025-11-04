"""
Tenant system configuration
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class TenantSystemConfig:
    """Configuration for the tenant system"""
    
    # Core settings
    enabled: bool = True
    auto_migration: bool = True
    
    # Default tenant settings  
    default_tenant_name: str = "Default Organization"
    default_tenant_domain: Optional[str] = None
    
    # Authentication settings
    require_email_verification: bool = False
    invitation_expiry_days: int = 7
    password_min_length: int = 8
    
    # Multi-tenancy settings
    allow_domain_based_routing: bool = True
    enforce_tenant_isolation: bool = True
    
    # Legacy compatibility
    maintain_legacy_tables: bool = True
    legacy_user_migration_enabled: bool = True
    
    # UI settings
    show_tenant_switcher: bool = False  # For future multi-tenant user support
    show_tenant_branding: bool = True
    
    # Security settings
    session_timeout_hours: int = 24
    max_failed_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TenantSystemConfig':
        """Create from dictionary"""
        return cls(**data)
    
    def validate(self) -> None:
        """Validate configuration"""
        if self.password_min_length < 4:
            raise ValueError("Password minimum length must be at least 4")
        
        if self.invitation_expiry_days < 1:
            raise ValueError("Invitation expiry must be at least 1 day")
        
        if self.session_timeout_hours < 1:
            raise ValueError("Session timeout must be at least 1 hour")


# Default configuration instance
DEFAULT_TENANT_CONFIG = TenantSystemConfig()


def get_tenant_config() -> TenantSystemConfig:
    """Get tenant system configuration"""
    # In a real application, this would load from environment variables,
    # configuration files, or database settings
    return DEFAULT_TENANT_CONFIG


def update_tenant_config(**kwargs) -> TenantSystemConfig:
    """Update tenant configuration"""
    config = get_tenant_config()
    
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    config.validate()
    return config


# Environment variable mappings for configuration
ENV_VAR_MAPPINGS = {
    'KH_ENABLE_TENANT_SYSTEM': 'enabled',
    'KH_TENANT_AUTO_MIGRATION': 'auto_migration',
    'KH_DEFAULT_TENANT_NAME': 'default_tenant_name',
    'KH_DEFAULT_TENANT_DOMAIN': 'default_tenant_domain',
    'KH_REQUIRE_EMAIL_VERIFICATION': 'require_email_verification',
    'KH_INVITATION_EXPIRY_DAYS': 'invitation_expiry_days',
    'KH_PASSWORD_MIN_LENGTH': 'password_min_length',
    'KH_ALLOW_DOMAIN_ROUTING': 'allow_domain_based_routing',
    'KH_ENFORCE_TENANT_ISOLATION': 'enforce_tenant_isolation',
    'KH_MAINTAIN_LEGACY_TABLES': 'maintain_legacy_tables',
    'KH_LEGACY_USER_MIGRATION': 'legacy_user_migration_enabled',
    'KH_SHOW_TENANT_SWITCHER': 'show_tenant_switcher',
    'KH_SHOW_TENANT_BRANDING': 'show_tenant_branding',
    'KH_SESSION_TIMEOUT_HOURS': 'session_timeout_hours',
    'KH_MAX_FAILED_LOGINS': 'max_failed_login_attempts',
    'KH_LOCKOUT_DURATION_MIN': 'lockout_duration_minutes',
}


def load_config_from_env() -> TenantSystemConfig:
    """Load configuration from environment variables"""
    import os
    
    config = TenantSystemConfig()
    
    for env_var, config_attr in ENV_VAR_MAPPINGS.items():
        env_value = os.getenv(env_var)
        if env_value is not None:
            # Get the current attribute to determine type
            current_value = getattr(config, config_attr)
            
            # Convert based on type
            if isinstance(current_value, bool):
                setattr(config, config_attr, env_value.lower() in ('true', '1', 'yes', 'on'))
            elif isinstance(current_value, int):
                setattr(config, config_attr, int(env_value))
            elif isinstance(current_value, str):
                setattr(config, config_attr, env_value)
            elif current_value is None:  # Optional strings
                setattr(config, config_attr, env_value if env_value else None)
    
    config.validate()
    return config
