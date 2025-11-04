import gradio as gr
from decouple import config
from ktem.app import BaseApp
from ktem.pages.chat import ChatPage
from ktem.pages.tenant_chat import TenantChatPage
from ktem.pages.help import HelpPage
from ktem.pages.resources import ResourcesTab
from ktem.pages.settings import SettingsPage
from ktem.pages.setup import SetupPage
from ktem.pages.tenant import TenantPage
from ktem.pages.tenant_login import TenantLoginPage
from ktem.services.tenant_auth import TenantAuthService, TenantAuthMiddleware
from ktem.utils.tenant_migration import run_migration_if_needed, ensure_default_tenant
from theflow.settings import settings as flowsettings

KH_DEMO_MODE = getattr(flowsettings, "KH_DEMO_MODE", False)
KH_SSO_ENABLED = getattr(flowsettings, "KH_SSO_ENABLED", False)
KH_ENABLE_FIRST_SETUP = getattr(flowsettings, "KH_ENABLE_FIRST_SETUP", False)
KH_APP_DATA_EXISTS = getattr(flowsettings, "KH_APP_DATA_EXISTS", True)
KH_ENABLE_TENANT_SYSTEM = getattr(flowsettings, "KH_ENABLE_TENANT_SYSTEM", True)

# override first setup setting
if config("KH_FIRST_SETUP", default=False, cast=bool):
    KH_APP_DATA_EXISTS = False

# Run tenant migration if needed on startup
if KH_ENABLE_TENANT_SYSTEM:
    try:
        migration_ran = run_migration_if_needed()
        if not migration_ran:
            # If no migration was needed, ensure default tenant exists
            ensure_default_tenant()
    except Exception as e:
        print(f"Warning: Tenant system initialization failed: {e}")
        print("Continuing with legacy system...")


def toggle_first_setup_visibility():
    global KH_APP_DATA_EXISTS
    is_first_setup = not KH_DEMO_MODE and not KH_APP_DATA_EXISTS
    KH_APP_DATA_EXISTS = True
    return gr.update(visible=is_first_setup), gr.update(visible=not is_first_setup)


class App(BaseApp):
    """The main app of Kotaemon

    The main application contains app-level information:
        - setting state
        - user id

    App life-cycle:
        - Render
        - Declare public events
        - Subscribe public events
        - Register events
    """

    def ui(self):
        """Render the UI"""
        self._tabs = {}

        # Add header with user info and logout button
        if self.f_user_management:
            with gr.Row(elem_classes=["header-row"]) as self.header:
                with gr.Column(scale=8):
                    self.user_info = gr.Markdown("", elem_classes=["user-info"])
                with gr.Column(scale=1, min_width=100):
                    self.logout_btn = gr.Button(
                        "🚪 Logout", 
                        elem_classes=["logout-btn"],
                        size="sm",
                        visible=False
                    )

        with gr.Tabs() as self.tabs:
            if self.f_user_management:
                # Use tenant login system if enabled
                if KH_ENABLE_TENANT_SYSTEM:
                    with gr.Tab(
                        "Welcome", elem_id="login-tab", id="login-tab"
                    ) as self._tabs["login-tab"]:
                        self.login_page = TenantLoginPage(self)
                else:
                    from ktem.pages.login import LoginPage
                    with gr.Tab(
                        "Welcome", elem_id="login-tab", id="login-tab"
                    ) as self._tabs["login-tab"]:
                        self.login_page = LoginPage(self)

            with gr.Tab(
                "Chat",
                elem_id="chat-tab",
                id="chat-tab",
                visible=not self.f_user_management,
            ) as self._tabs["chat-tab"]:
                # Use tenant-aware chat page if tenant system is enabled
                if KH_ENABLE_TENANT_SYSTEM:
                    self.chat_page = TenantChatPage(self)
                else:
                    self.chat_page = ChatPage(self)

            with gr.Tab(
                "Tenant",
                elem_id="tenant-tab",
                id="tenant-tab",
                visible=not self.f_user_management,
            ) as self._tabs["tenant-tab"]:
                self.tenant_page = TenantPage(self)

            if len(self.index_manager.indices) == 1:
                for index in self.index_manager.indices:
                    with gr.Tab(
                        f"{index.name}",
                        elem_id="indices-tab",
                        elem_classes=[
                            "fill-main-area-height",
                            "scrollable",
                            "indices-tab",
                        ],
                        id="indices-tab",
                        visible=not self.f_user_management and not KH_DEMO_MODE,
                    ) as self._tabs[f"{index.id}-tab"]:
                        page = index.get_index_page_ui()
                        setattr(self, f"_index_{index.id}", page)
            elif len(self.index_manager.indices) > 1:
                with gr.Tab(
                    "Files",
                    elem_id="indices-tab",
                    elem_classes=["fill-main-area-height", "scrollable", "indices-tab"],
                    id="indices-tab",
                    visible=not self.f_user_management and not KH_DEMO_MODE,
                ) as self._tabs["indices-tab"]:
                    for index in self.index_manager.indices:
                        with gr.Tab(
                            index.name,
                            elem_id=f"{index.id}-tab",
                        ) as self._tabs[f"{index.id}-tab"]:
                            page = index.get_index_page_ui()
                            setattr(self, f"_index_{index.id}", page)

            if not KH_DEMO_MODE:
                if not KH_SSO_ENABLED:
                    with gr.Tab(
                        "Resources",
                        elem_id="resources-tab",
                        id="resources-tab",
                        visible=not self.f_user_management,
                        elem_classes=["fill-main-area-height", "scrollable"],
                    ) as self._tabs["resources-tab"]:
                        self.resources_page = ResourcesTab(self)

                with gr.Tab(
                    "Settings",
                    elem_id="settings-tab",
                    id="settings-tab",
                    visible=not self.f_user_management,
                    elem_classes=["fill-main-area-height", "scrollable"],
                ) as self._tabs["settings-tab"]:
                    self.settings_page = SettingsPage(self)

            with gr.Tab(
                "Help",
                elem_id="help-tab",
                id="help-tab",
                visible=not self.f_user_management,
                elem_classes=["fill-main-area-height", "scrollable"],
            ) as self._tabs["help-tab"]:
                self.help_page = HelpPage(self)

        if KH_ENABLE_FIRST_SETUP:
            with gr.Column(visible=False) as self.setup_page_wrapper:
                self.setup_page = SetupPage(self)

    def on_subscribe_public_events(self):
        if self.f_user_management:
            def toggle_login_visibility(user_id):
                if not user_id:
                    tabs_result = list(
                        (
                            gr.update(visible=True)
                            if k == "login-tab"
                            else gr.update(visible=False)
                        )
                        for k in self._tabs.keys()
                    ) + [gr.update(selected="login-tab")]
                    
                    # Hide header when logged out
                    header_result = [
                        gr.update(value="", visible=False),  # user_info
                        gr.update(visible=False)  # logout_btn
                    ]
                    
                    return tabs_result + header_result

                # Use tenant system if enabled
                if KH_ENABLE_TENANT_SYSTEM:
                    auth_user = TenantAuthService.get_user_by_id(user_id)
                    if auth_user is None:
                        tabs_result = list(
                            (
                                gr.update(visible=True)
                                if k == "login-tab"
                                else gr.update(visible=False)
                            )
                            for k in self._tabs.keys()
                        ) + [gr.update(selected="login-tab")]
                        
                        # Hide header when auth fails
                        header_result = [
                            gr.update(value="", visible=False),  # user_info
                            gr.update(visible=False)  # logout_btn
                        ]
                        
                        return tabs_result + header_result
                    
                    # Role-based access control
                    is_super_admin = auth_user.is_super_admin
                    is_admin = auth_user.is_admin
                    is_user = auth_user.role.value == "user"
                else:
                    # Legacy user system
                    from ktem.db.engine import engine
                    from ktem.db.models import User
                    from sqlmodel import Session, select
                    
                    with Session(engine) as session:
                        user = session.exec(select(User).where(User.id == user_id)).first()
                        if user is None:
                            tabs_result = list(
                                (
                                    gr.update(visible=True)
                                    if k == "login-tab"
                                    else gr.update(visible=False)
                                )
                                for k in self._tabs.keys()
                            ) + [gr.update(selected="login-tab")]
                            
                            # Hide header when legacy auth fails
                            header_result = [
                                gr.update(value="", visible=False),  # user_info
                                gr.update(visible=False)  # logout_btn
                            ]
                            
                            return tabs_result + header_result

                        # Legacy system - treat legacy admin as super admin for compatibility
                        is_super_admin = user.admin
                        is_admin = user.admin
                        is_user = not user.admin

                tabs_update = []
                for k in self._tabs.keys():
                    if k == "login-tab":
                        tabs_update.append(gr.update(visible=False))
                    elif k == "tenant-tab":
                        # Only super admin can see tenant tab
                        tabs_update.append(gr.update(visible=is_super_admin))
                    elif k == "resources-tab":
                        # Admin and super admin can see resources
                        tabs_update.append(gr.update(visible=is_admin))
                    elif k == "settings-tab":
                        # Admin and super admin can see settings
                        tabs_update.append(gr.update(visible=is_admin))
                    elif k == "help-tab":
                        # Admin and super admin can see help
                        tabs_update.append(gr.update(visible=is_admin))
                    elif "indices-tab" in k:
                        # Admin and super admin can see file/indices tabs
                        tabs_update.append(gr.update(visible=is_admin))
                    elif k == "chat-tab":
                        # Everyone can see chat
                        tabs_update.append(gr.update(visible=True))
                    else:
                        # Default: show to admin and super admin
                        tabs_update.append(gr.update(visible=is_admin))

                tabs_update.append(gr.update(selected="chat-tab"))

                # Add header updates for successful login
                if KH_ENABLE_TENANT_SYSTEM:
                    # Show user info with role
                    role_display = auth_user.role.value.replace('_', ' ').title()
                    user_info_text = f"**{auth_user.username}** ({role_display}) • {auth_user.tenant_name}"
                else:
                    # Legacy system
                    role_display = "Admin" if user.admin else "User"
                    user_info_text = f"**{user.username}** ({role_display})"
                
                header_result = [
                    gr.update(value=user_info_text, visible=True),  # user_info
                    gr.update(visible=True)  # logout_btn
                ]

                return tabs_update + header_result

            self.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": toggle_login_visibility,
                    "inputs": [self.user_id],
                    "outputs": list(self._tabs.values()) + [self.tabs] + [self.user_info, self.logout_btn],
                    "show_progress": "hidden",
                },
            )

            self.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": toggle_login_visibility,
                    "inputs": [self.user_id],
                    "outputs": list(self._tabs.values()) + [self.tabs] + [self.user_info, self.logout_btn],
                    "show_progress": "hidden",
                },
            )
            
            # Add logout button functionality
            def handle_logout():
                # Clear user session
                return None
            
            self.logout_btn.click(
                fn=handle_logout,
                outputs=[self.user_id],
                show_progress="hidden"
            ).then(
                fn=toggle_login_visibility,
                inputs=[self.user_id],
                outputs=list(self._tabs.values()) + [self.tabs] + [self.user_info, self.logout_btn],
                show_progress="hidden"
            )

        if KH_ENABLE_FIRST_SETUP:
            self.subscribe_event(
                name="onFirstSetupComplete",
                definition={
                    "fn": toggle_first_setup_visibility,
                    "inputs": [],
                    "outputs": [self.setup_page_wrapper, self.tabs],
                    "show_progress": "hidden",
                },
            )

    def _on_app_created(self):
        """Called when the app is created"""

        if KH_ENABLE_FIRST_SETUP:
            self.app.load(
                toggle_first_setup_visibility,
                inputs=[],
                outputs=[self.setup_page_wrapper, self.tabs],
            )
