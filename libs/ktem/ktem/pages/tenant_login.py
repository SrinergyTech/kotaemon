import hashlib
import gradio as gr
from typing import Optional

from ktem.app import BasePage
from ktem.db.models import User, TenantUser, Tenant, engine
from ktem.services.tenant_auth import TenantAuthService, AuthUser
from ktem.pages.resources.user import create_user
from sqlmodel import Session, select


# JavaScript for credential management
fetch_creds = """
function() {
    const username = getStorage('username', '')
    const password = getStorage('password', '')
    const tenant = getStorage('tenant_domain', '')
    return [username, password, tenant, null];
}
"""

signin_js = """
function(usn, pwd, tenant) {
    setStorage('username', usn);
    setStorage('password', pwd);
    setStorage('tenant_domain', tenant);
    return [usn, pwd, tenant];
}
"""


class TenantLoginPage(BasePage):
    """Enhanced login page with tenant support"""

    public_events = ["onSignIn", "onTenantSignIn"]

    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        """Build the tenant-aware login UI"""
        with gr.Column():
            gr.Markdown(f"# Welcome to {self._app.app_name}!")
            gr.Markdown("### Multi-Tenant Authentication")
            
            # Login mode selection
            with gr.Row():
                self.login_mode = gr.Radio(
                    choices=[("Single Tenant", "single"), ("Multi-Tenant", "multi")],
                    label="Login Mode",
                    value="single",
                    visible=True
                )
            
            # Login form
            with gr.Group():
                self.usn = gr.Textbox(
                    label="Username or Email",
                    placeholder="Enter your username or email",
                    visible=False
                )
                self.pwd = gr.Textbox(
                    label="Password",
                    type="password",
                    placeholder="Enter your password",
                    visible=False
                )
                
                # Tenant domain (for multi-tenant mode)
                self.tenant_domain = gr.Textbox(
                    label="Tenant Domain",
                    placeholder="your-company.example.com (optional)",
                    visible=False
                )
                
                self.btn_login = gr.Button("Sign In", variant="primary", visible=False)
            
            # Registration/Invitation section
            with gr.Group(visible=False) as self.registration_section:
                gr.Markdown("### Join with Invitation")
                with gr.Row():
                    self.invitation_token = gr.Textbox(
                        label="Invitation Token",
                        placeholder="Enter your invitation token"
                    )
                with gr.Row():
                    self.reg_username = gr.Textbox(
                        label="Choose Username",
                        placeholder="Enter desired username"
                    )
                    self.reg_password = gr.Textbox(
                        label="Choose Password",
                        type="password",
                        placeholder="Enter password"
                    )
                self.btn_accept_invitation = gr.Button("Accept Invitation", variant="primary")
            
            # Admin section for creating first tenant
            with gr.Group(visible=False) as self.admin_setup_section:
                gr.Markdown("### System Setup - Create First Tenant")
                gr.Markdown("*No tenants exist. Create the first tenant and admin user.*")
                
                with gr.Row():
                    self.setup_tenant_name = gr.Textbox(
                        label="Tenant Name",
                        placeholder="Your Organization"
                    )
                    self.setup_tenant_domain = gr.Textbox(
                        label="Tenant Domain (Optional)",
                        placeholder="yourorg.example.com"
                    )
                
                with gr.Row():
                    self.setup_admin_username = gr.Textbox(
                        label="Admin Username",
                        placeholder="admin"
                    )
                    self.setup_admin_email = gr.Textbox(
                        label="Admin Email",
                        placeholder="admin@yourorg.com"
                    )
                
                self.setup_admin_password = gr.Textbox(
                    label="Admin Password",
                    type="password",
                    placeholder="Choose a strong password"
                )
                
                self.btn_create_tenant = gr.Button("Create Tenant & Admin", variant="primary")
            
            # Toggle buttons
            with gr.Row():
                self.btn_show_invitation = gr.Button("Have an invitation?", variant="secondary", visible=False)
                self.btn_show_login = gr.Button("Back to Login", variant="secondary", visible=False)
            
            # Status messages
            self.status_message = gr.Markdown("", visible=False, elem_classes=["status-message"])

    def on_register_events(self):
        """Register event handlers"""
        # Login mode change
        self.login_mode.change(
            self._on_login_mode_change,
            inputs=[self.login_mode],
            outputs=[self.tenant_domain]
        )
        
        # Main login flow
        login_event = gr.on(
            triggers=[self.btn_login.click, self.pwd.submit],
            fn=self._tenant_login,
            inputs=[self.usn, self.pwd, self.tenant_domain],
            outputs=[self._app.user_id, self.usn, self.pwd, self.tenant_domain, self.status_message],
            show_progress="hidden",
            js=signin_js,
        ).then(
            self._toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[
                self.usn, self.pwd, self.tenant_domain, 
                self.btn_login, self.login_mode,
                self.registration_section, self.admin_setup_section
            ],
        )
        
        # Propagate to app events
        for event in self._app.get_event("onSignIn"):
            login_event = login_event.success(**event)
        
        # Invitation acceptance
        self.btn_accept_invitation.click(
            self._accept_invitation,
            inputs=[self.invitation_token, self.reg_username, self.reg_password],
            outputs=[self._app.user_id, self.status_message]
        ).then(
            self._toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[
                self.usn, self.pwd, self.tenant_domain,
                self.btn_login, self.login_mode,
                self.registration_section, self.admin_setup_section
            ]
        )
        
        # Create first tenant
        self.btn_create_tenant.click(
            self._create_first_tenant,
            inputs=[
                self.setup_tenant_name, self.setup_tenant_domain,
                self.setup_admin_username, self.setup_admin_email, self.setup_admin_password
            ],
            outputs=[self._app.user_id, self.status_message]
        ).then(
            self._toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[
                self.usn, self.pwd, self.tenant_domain,
                self.btn_login, self.login_mode,
                self.registration_section, self.admin_setup_section
            ]
        )
        
        # Toggle sections
        self.btn_show_invitation.click(
            lambda: (gr.update(visible=False), gr.update(visible=True), gr.update(visible=True)),
            outputs=[self.admin_setup_section, self.registration_section, self.btn_show_login]
        )
        
        self.btn_show_login.click(
            lambda: (gr.update(visible=False), gr.update(visible=False)),
            outputs=[self.registration_section, self.btn_show_login]
        )

    def _on_app_created(self):
        """Called when app is created"""
        # Load saved credentials and check system state
        onSignIn = self._app.app.load(
            self._load_initial_state,
            inputs=[self.usn, self.pwd, self.tenant_domain],
            outputs=[
                self._app.user_id, self.usn, self.pwd, self.tenant_domain,
                self.status_message
            ],
            show_progress="hidden",
            js=fetch_creds,
        ).then(
            self._toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[
                self.usn, self.pwd, self.tenant_domain,
                self.btn_login, self.login_mode,
                self.registration_section, self.admin_setup_section
            ],
        )
        
        # Propagate to app events
        for event in self._app.get_event("onSignIn"):
            onSignIn = onSignIn.success(**event)

    def on_subscribe_public_events(self):
        """Subscribe to public events"""
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": self._toggle_login_visibility,
                "inputs": [self._app.user_id],
                "outputs": [
                    self.usn, self.pwd, self.tenant_domain,
                    self.btn_login, self.login_mode,
                    self.registration_section, self.admin_setup_section
                ],
                "show_progress": "hidden",
            },
        )

    def _on_login_mode_change(self, mode: str):
        """Handle login mode change"""
        return gr.update(visible=(mode == "multi"))

    def _load_initial_state(self, usn: str, pwd: str, tenant: str):
        """Load initial state and try auto-login"""
        # Check if system needs setup
        if self._needs_setup():
            return None, "", "", "", gr.update(visible=False)
        
        # Try auto-login if credentials exist
        if usn and pwd:
            return self._tenant_login(usn, pwd, tenant)
        
        return None, usn, pwd, tenant, gr.update(visible=False)

    def _needs_setup(self) -> bool:
        """Check if system needs initial setup"""
        with Session(engine) as session:
            tenant_count = len(list(session.exec(select(Tenant)).all()))
            return tenant_count == 0

    def _tenant_login(self, username: str, password: str, tenant_domain: str, request: gr.Request = None):
        """Enhanced login with tenant support"""
        # Try SSO first (existing gradiologin support)
        try:
            import gradiologin as grlogin
            user = grlogin.get_user(request)
        except (ImportError, AssertionError):
            user = None

        if user:
            # SSO flow - need to map to tenant user
            return self._handle_sso_login(user)
        
        # Regular login flow
        if not username or not password:
            return None, username, password, tenant_domain, gr.update(visible=False)

        # Authenticate with tenant service
        auth_user = TenantAuthService.authenticate_user(
            username=username,
            password=password,
            tenant_domain=tenant_domain or None
        )

        if auth_user:
            # Successful login
            return (
                auth_user.id,
                "",  # Clear credentials
                "",
                "",
                gr.update(
                    value=f"✅ **Welcome back, {auth_user.username}!** Signed in to {auth_user.tenant_name}",
                    visible=True
                )
            )
        
        # Failed login
        return (
            None,
            username,
            password,
            tenant_domain,
            gr.update(value="❌ **Error:** Invalid credentials or inactive account.", visible=True)
        )

    def _handle_sso_login(self, sso_user: dict):
        """Handle SSO user login"""
        user_id = sso_user["sub"]
        
        # Try to find existing tenant user
        auth_user = TenantAuthService.get_user_by_id(user_id)
        
        if auth_user:
            return (
                auth_user.id,
                "", "", "",
                gr.update(
                    value=f"✅ **Welcome back, {auth_user.username}!**",
                    visible=True
                )
            )
        
        # For SSO, we need to handle tenant assignment differently
        # This is a simplified version - in production you'd want more sophisticated tenant mapping
        return (
            None, "", "", "",
            gr.update(
                value="❌ **Error:** SSO user not mapped to any tenant. Contact administrator.",
                visible=True
            )
        )

    def _accept_invitation(self, token: str, username: str, password: str):
        """Accept a tenant invitation"""
        if not token or not username or not password:
            return (
                None,
                gr.update(value="❌ **Error:** All fields are required.", visible=True)
            )
        
        try:
            user = TenantAuthService.accept_invitation(token, username, password)
            
            if user:
                return (
                    user.id,
                    gr.update(
                        value=f"✅ **Success!** Welcome to the team, {user.username}!",
                        visible=True
                    )
                )
            else:
                return (
                    None,
                    gr.update(
                        value="❌ **Error:** Invalid or expired invitation token.",
                        visible=True
                    )
                )
        except Exception as e:
            return (
                None,
                gr.update(value=f"❌ **Error:** {str(e)}", visible=True)
            )

    def _create_first_tenant(self, tenant_name: str, tenant_domain: str, 
                           admin_username: str, admin_email: str, admin_password: str):
        """Create the first tenant and admin user"""
        if not all([tenant_name, admin_username, admin_email, admin_password]):
            return (
                None,
                gr.update(value="❌ **Error:** All fields are required.", visible=True)
            )
        
        try:
            # Check if system still needs setup
            if not self._needs_setup():
                return (
                    None,
                    gr.update(value="❌ **Error:** System already has tenants configured.", visible=True)
                )
            
            tenant, admin_user = TenantAuthService.create_tenant(
                name=tenant_name,
                domain=tenant_domain or None,
                admin_username=admin_username,
                admin_email=admin_email,
                admin_password=admin_password
            )
            
            return (
                admin_user.id,
                gr.update(
                    value=f"✅ **Success!** Tenant '{tenant.name}' created. Welcome, {admin_user.username}!",
                    visible=True
                )
            )
            
        except Exception as e:
            return (
                None,
                gr.update(value=f"❌ **Error:** Failed to create tenant: {str(e)}", visible=True)
            )

    def _toggle_login_visibility(self, user_id: str):
        """Toggle visibility based on authentication state"""
        authenticated = user_id is not None
        needs_setup = not authenticated and self._needs_setup()
        
        return (
            gr.update(visible=not authenticated),  # usn
            gr.update(visible=not authenticated),  # pwd
            gr.update(visible=not authenticated),  # tenant_domain
            gr.update(visible=not authenticated),  # btn_login
            gr.update(visible=not authenticated),  # login_mode
            gr.update(visible=False),              # registration_section
            gr.update(visible=needs_setup)  # admin_setup_section
        )
