import gradio as gr
from typing import Optional

from ktem.pages.chat import ChatPage
from ktem.services.tenant_auth import TenantAuthService, TenantAuthMiddleware, AuthUser


class TenantChatPage(ChatPage):
    """Tenant-aware chat page that extends the base chat page with tenant context"""
    
    def __init__(self, app):
        self.current_user: Optional[AuthUser] = None
        self.tenant_context = None
        self.tenant_features_group = None
        self._tenant_events_registered = False
        super().__init__(app)
    
    def render(self):
        """Render tenant-aware chat interface"""
        # Add tenant context header
        with gr.Row(elem_classes=["tenant-header"]):
            self.tenant_context = gr.Markdown("", elem_classes=["tenant-info"])
        
        # Render base chat interface
        super().render()
        
        # Add tenant-specific features
        self._render_tenant_features()
        
        # Register tenant events after rendering
        self._register_tenant_events()
    
    def _render_tenant_features(self):
        """Add tenant-specific chat features"""
        with gr.Group(visible=False, elem_classes=["tenant-features"]) as self.tenant_features_group:
            with gr.Row():
                gr.Markdown("### Tenant Features")
                self.share_in_tenant = gr.Checkbox(
                    label="Share with tenant members",
                    info="Allow other members of your tenant to see this conversation",
                    value=False
                )
    
    def _register_tenant_events(self):
        """Register tenant-specific events after UI is ready"""
        if not self._tenant_events_registered and self.tenant_context and self.tenant_features_group:
            self._app.app.load(
                self._load_tenant_context,
                inputs=[self._app.user_id],
                outputs=[self.tenant_context, self.tenant_features_group]
            )
            self._tenant_events_registered = True
    
    def on_register_events(self):
        """Register events - base events only"""
        # Only register base chat events here
        super().on_register_events()
    
    def _load_tenant_context(self, user_id: str):
        """Load tenant context for the current user"""
        if not user_id:
            return (
                gr.update(value="**Please sign in to access chat**"),
                gr.update(visible=False)
            )
        
        self.current_user = TenantAuthService.get_user_by_id(user_id)
        
        if not self.current_user:
            return (
                gr.update(value="**User not found**"),
                gr.update(visible=False)
            )
        
        # Create tenant context display
        context_info = f"""
**🏢 Tenant:** {self.current_user.tenant_name} | **👤 Role:** {self.current_user.role.value.title()} | **📧 {self.current_user.email}**
"""
        
        return (
            gr.update(value=context_info),
            gr.update(visible=True)
        )
    
    def _get_user_context(self) -> Optional[AuthUser]:
        """Get current user context"""
        return self.current_user
    
    def _can_access_conversation(self, conversation_id: str) -> bool:
        """Check if user can access a specific conversation"""
        if not self.current_user:
            return False
        
        # Implement tenant-based conversation access control
        # This would check if the conversation belongs to the user's tenant
        return TenantAuthMiddleware.require_auth(self.current_user)
    
    def _filter_conversations_by_tenant(self, conversations: list) -> list:
        """Filter conversations based on tenant membership"""
        if not self.current_user:
            return []
        
        # Filter conversations to only show those from the user's tenant
        # This would be implemented based on your conversation storage structure
        return conversations
