import gradio as gr
from typing import Optional, List, Dict, Any
import json

from ktem.app import BasePage
from ktem.services.tenant_auth import TenantAuthService, TenantAuthMiddleware, AuthUser
from ktem.db.models import Tenant, TenantUser, TenantInvitation, engine
from ktem.db.tenant_models import UserRole, TenantStatus
from sqlmodel import Session, select


class TenantPage(BasePage):
    def __init__(self, app):
        self._app = app
        self.current_user: Optional[AuthUser] = None
        self.render()

    def render(self):
        """Render the tenant management UI"""
        with gr.Column() as self.main_container:
            # Header
            with gr.Row():
                gr.Markdown("# Tenant Management")
                with gr.Column(scale=1, min_width=200):
                    self.tenant_info = gr.Markdown("", elem_classes=["tenant-info"])
            
            gr.Markdown("---")
            
            # Tabs for different management sections
            with gr.Tabs() as self.management_tabs:
                # User Management Tab
                with gr.Tab("User Management", id="users") as self.users_tab:
                    self._render_user_management()
                
                # Invitations Tab
                with gr.Tab("Invitations", id="invitations") as self.invitations_tab:
                    self._render_invitation_management()
                
                # Tenant Settings Tab  
                with gr.Tab("Tenant Settings", id="settings") as self.settings_tab:
                    self._render_tenant_settings()
            
            # Status messages
            self.status_message = gr.Markdown("", visible=False, elem_classes=["status-message"])

    def _render_user_management(self):
        """Render user management interface"""
        with gr.Column():
            gr.Markdown("## Users in Your Tenant")
            
            # Add new user section (admin only)
            with gr.Group(visible=False) as self.add_user_section:
                gr.Markdown("### Add New User")
                with gr.Row():
                    self.new_username = gr.Textbox(label="Username", placeholder="Enter username")
                    self.new_email = gr.Textbox(label="Email", placeholder="user@example.com")
                with gr.Row():
                    self.new_password = gr.Textbox(label="Password", type="password")
                    self.new_role = gr.Dropdown(
                        choices=[("User", "user"), ("Admin", "admin")],
                        label="Role",
                        value="user"
                    )
                self.add_user_btn = gr.Button("Add User", variant="primary")
            
            # Users table
            self.users_table = gr.DataFrame(
                headers=["ID", "Username", "Email", "Role", "Status", "Last Login", "Actions"],
                datatype=["str", "str", "str", "str", "str", "str", "str"],
                interactive=False,
                wrap=True
            )
            
            # User management buttons
            with gr.Row():
                self.refresh_users_btn = gr.Button("Refresh", variant="secondary")
                self.deactivate_user_btn = gr.Button("Deactivate Selected", variant="stop", visible=False)
                
            # Edit user modal components
            with gr.Group(visible=False) as self.edit_user_modal:
                gr.Markdown("### Edit User")
                self.edit_user_id = gr.Textbox(visible=False)
                self.edit_username = gr.Textbox(label="Username")
                self.edit_email = gr.Textbox(label="Email")
                self.edit_role = gr.Dropdown(
                    choices=[("User", "user"), ("Admin", "admin")],
                    label="Role"
                )
                with gr.Row():
                    self.save_user_btn = gr.Button("Save Changes", variant="primary")
                    self.cancel_edit_btn = gr.Button("Cancel", variant="secondary")

    def _render_invitation_management(self):
        """Render invitation management interface"""
        with gr.Column():
            gr.Markdown("## Tenant Invitations")
            
            # Send invitation section (admin only)
            with gr.Group(visible=False) as self.send_invitation_section:
                gr.Markdown("### Send Invitation")
                with gr.Row():
                    self.invite_email = gr.Textbox(label="Email", placeholder="user@example.com")
                    self.invite_role = gr.Dropdown(
                        choices=[("User", "user"), ("Admin", "admin")],
                        label="Role",
                        value="user"
                    )
                self.send_invite_btn = gr.Button("Send Invitation", variant="primary")
            
            # Invitations table
            self.invitations_table = gr.DataFrame(
                headers=["Email", "Role", "Status", "Sent Date", "Expires", "Actions"],
                datatype=["str", "str", "str", "str", "str", "str"],
                interactive=False,
                wrap=True
            )
            
            self.refresh_invitations_btn = gr.Button("Refresh", variant="secondary")

    def _render_tenant_settings(self):
        """Render tenant settings interface"""
        with gr.Column():
            gr.Markdown("## Tenant Configuration")
            
            # Tenant info (admin only)
            with gr.Group(visible=False) as self.tenant_settings_section:
                gr.Markdown("### Basic Information")
                self.tenant_name = gr.Textbox(label="Tenant Name")
                self.tenant_domain = gr.Textbox(label="Domain", placeholder="Optional custom domain")
                self.tenant_status = gr.Dropdown(
                    choices=[("Active", "active"), ("Suspended", "suspended"), ("Inactive", "inactive")],
                    label="Status"
                )
                
                gr.Markdown("### Tenant Settings")
                self.tenant_settings_json = gr.Code(
                    label="Tenant Settings (JSON)",
                    language="json",
                    lines=10
                )
                
                self.save_tenant_btn = gr.Button("Save Tenant Settings", variant="primary")
            
            # Read-only tenant info for non-admins
            with gr.Group(visible=True) as self.tenant_info_readonly:
                self.readonly_tenant_info = gr.Markdown("")

    def on_register_events(self):
        """Register event handlers"""
        # Load user context and update UI
        self._app.app.load(
            self._load_user_context,
            inputs=[self._app.user_id],
            outputs=[
                self.tenant_info, 
                self.add_user_section,
                self.send_invitation_section,
                self.tenant_settings_section,
                self.tenant_info_readonly,
                self.deactivate_user_btn
            ]
        ).then(
            self._load_users_data,
            outputs=[self.users_table]
        ).then(
            self._load_invitations_data,
            outputs=[self.invitations_table]
        )
        
        # User management events
        self.add_user_btn.click(
            self._add_user,
            inputs=[self.new_username, self.new_email, self.new_password, self.new_role],
            outputs=[self.status_message, self.users_table]
        )
        
        self.refresh_users_btn.click(
            self._load_users_data,
            outputs=[self.users_table]
        )
        
        # Invitation events
        self.send_invite_btn.click(
            self._send_invitation,
            inputs=[self.invite_email, self.invite_role],
            outputs=[self.status_message, self.invitations_table]
        )
        
        self.refresh_invitations_btn.click(
            self._load_invitations_data,
            outputs=[self.invitations_table]
        )
        
        # Tenant settings events
        self.save_tenant_btn.click(
            self._save_tenant_settings,
            inputs=[self.tenant_name, self.tenant_domain, self.tenant_status, self.tenant_settings_json],
            outputs=[self.status_message]
        )

    def _load_user_context(self, user_id: str):
        """Load current user context and determine permissions"""
        if not user_id:
            return (
                "**Not authenticated**", 
                gr.update(visible=False),  # add_user_section
                gr.update(visible=False),  # send_invitation_section  
                gr.update(visible=False),  # tenant_settings_section
                gr.update(visible=True),   # tenant_info_readonly
                gr.update(visible=False)   # deactivate_user_btn
            )
        
        self.current_user = TenantAuthService.get_user_by_id(user_id)
        
        if not self.current_user:
            return (
                "**User not found**",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False), 
                gr.update(visible=True),
                gr.update(visible=False)
            )
        
        # Update tenant info
        tenant_info = f"""
**Tenant:** {self.current_user.tenant_name}  
**Your Role:** {self.current_user.role.value.title()}  
**Status:** Active
"""
        
        readonly_info = f"""
### Your Tenant Information
- **Name:** {self.current_user.tenant_name}
- **Your Role:** {self.current_user.role.value.title()}
- **Your Username:** {self.current_user.username}
- **Your Email:** {self.current_user.email}

*Contact your tenant administrator to modify tenant settings or manage users.*
"""
        
        is_admin = self.current_user.is_admin
        
        return (
            tenant_info,
            gr.update(visible=is_admin),      # add_user_section
            gr.update(visible=is_admin),      # send_invitation_section
            gr.update(visible=is_admin),      # tenant_settings_section
            gr.update(visible=not is_admin, value=readonly_info if not is_admin else ""),  # tenant_info_readonly
            gr.update(visible=is_admin)       # deactivate_user_btn
        )

    def _load_users_data(self):
        """Load users data for the table"""
        if not self.current_user:
            return gr.update(value=[])
        
        try:
            users = TenantAuthService.get_tenant_users(self.current_user.tenant_id)
            
            data = []
            for user in users:
                last_login = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "Never"
                status = "Active" if user.is_active else "Inactive"
                actions = "Edit | Deactivate" if user.is_active and user.id != self.current_user.id else "View"
                
                data.append([
                    user.id[:8] + "...",  # Shortened ID
                    user.username,
                    user.email,
                    user.role.value.title(),
                    status,
                    last_login,
                    actions
                ])
            
            return gr.update(value=data)
        except Exception as e:
            print(f"Error loading users: {e}")
            return gr.update(value=[])

    def _load_invitations_data(self):
        """Load invitations data for the table"""
        if not self.current_user or not self.current_user.is_admin:
            return gr.update(value=[])
        
        try:
            with Session(engine) as session:
                invitations = session.exec(
                    select(TenantInvitation).where(
                        TenantInvitation.tenant_id == self.current_user.tenant_id
                    )
                ).all()
                
                data = []
                for invite in invitations:
                    status = "Used" if invite.is_used else "Pending"
                    sent_date = invite.date_created.strftime("%Y-%m-%d")
                    expires = invite.expires_at.strftime("%Y-%m-%d")
                    actions = "Resend" if not invite.is_used else "View"
                    
                    data.append([
                        invite.email,
                        invite.role.value.title(),
                        status,
                        sent_date,
                        expires,
                        actions
                    ])
                
                return gr.update(value=data)
        except Exception as e:
            print(f"Error loading invitations: {e}")
            return gr.update(value=[])

    def _add_user(self, username: str, email: str, password: str, role: str):
        """Add a new user to the tenant"""
        if not TenantAuthMiddleware.require_admin(self.current_user):
            return gr.update(value="❌ **Error:** You don't have permission to add users.", visible=True), gr.update()
        
        if not username or not email or not password:
            return gr.update(value="❌ **Error:** All fields are required.", visible=True), gr.update()
        
        try:
            user_role = UserRole.ADMIN if role == "admin" else UserRole.USER
            TenantAuthService.create_user(
                tenant_id=self.current_user.tenant_id,
                username=username,
                email=email,
                password=password,
                role=user_role,
                created_by=self.current_user.id
            )
            
            # Reload users table
            users_update = self._load_users_data()
            
            return (
                gr.update(value="✅ **Success:** User added successfully!", visible=True),
                users_update
            )
        except Exception as e:
            return (
                gr.update(value=f"❌ **Error:** Failed to add user: {str(e)}", visible=True),
                gr.update()
            )

    def _send_invitation(self, email: str, role: str):
        """Send an invitation to join the tenant"""
        if not TenantAuthMiddleware.require_admin(self.current_user):
            return gr.update(value="❌ **Error:** You don't have permission to send invitations.", visible=True), gr.update()
        
        if not email:
            return gr.update(value="❌ **Error:** Email is required.", visible=True), gr.update()
        
        try:
            user_role = UserRole.ADMIN if role == "admin" else UserRole.USER
            invitation = TenantAuthService.invite_user(
                tenant_id=self.current_user.tenant_id,
                email=email,
                role=user_role,
                invited_by=self.current_user.id
            )
            
            # Reload invitations table
            invitations_update = self._load_invitations_data()
            
            return (
                gr.update(value=f"✅ **Success:** Invitation sent to {email}. Token: {invitation.token}", visible=True),
                invitations_update
            )
        except Exception as e:
            return (
                gr.update(value=f"❌ **Error:** Failed to send invitation: {str(e)}", visible=True),
                gr.update()
            )

    def _save_tenant_settings(self, name: str, domain: str, status: str, settings_json: str):
        """Save tenant settings"""
        if not TenantAuthMiddleware.require_admin(self.current_user):
            return gr.update(value="❌ **Error:** You don't have permission to modify tenant settings.", visible=True)
        
        try:
            # Parse settings JSON
            settings_dict = {}
            if settings_json.strip():
                settings_dict = json.loads(settings_json)
            
            with Session(engine) as session:
                tenant = session.get(Tenant, self.current_user.tenant_id)
                if tenant:
                    tenant.name = name or tenant.name
                    tenant.domain = domain or None
                    tenant.status = TenantStatus(status) if status else tenant.status
                    tenant.settings = settings_dict
                    
                    session.add(tenant)
                    session.commit()
                    
                    return gr.update(value="✅ **Success:** Tenant settings saved successfully!", visible=True)
            
            return gr.update(value="❌ **Error:** Tenant not found.", visible=True)
            
        except json.JSONDecodeError:
            return gr.update(value="❌ **Error:** Invalid JSON in settings.", visible=True)
        except Exception as e:
            return gr.update(value=f"❌ **Error:** Failed to save settings: {str(e)}", visible=True)
