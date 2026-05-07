"""Pre-built site provisioning templates.

Each SiteTemplate bundles a name, description, trigger keywords, and a
factory function that returns a fresh ProvisioningBlueprint so callers
always get an independent (mutable) copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from src.domain.entities.core import ActionType, ProvisioningBlueprint, SPPage, SPSite
from src.domain.value_objects import SPColumn, WebPart


# ---------------------------------------------------------------------------
# Helper: build a default welcome WebPart for any page
# ---------------------------------------------------------------------------

def _welcome_wp(title: str) -> WebPart:
    return WebPart(
        type="Hero",
        properties={"title": title},
        webpart_type="Hero",
    )


def _text_wp(content: str) -> WebPart:
    return WebPart(
        type="Text",
        properties={"content": content},
        webpart_type="Text",
    )


# ---------------------------------------------------------------------------
# Template factories
# Each returns a fresh ProvisioningBlueprint so state is never shared.
# ---------------------------------------------------------------------------

def _hr_intranet_blueprint() -> ProvisioningBlueprint:
    from src.domain.entities.document import DocumentLibrary
    from src.domain.entities.security import SharePointGroup

    site = SPSite(
        title="HR Portal",
        description="Central HR information hub for all employees.",
        name="hr-portal",
        template="sitepagepublishing",
        action=ActionType.CREATE,
    )
    pages = [
        SPPage(title="Welcome", layout="home", action=ActionType.CREATE, webparts=[
            _welcome_wp("Welcome to HR"), _text_wp("<p>Your people, policies, and resources — all in one place.</p>")
        ]),
        SPPage(title="Policies", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("HR Policies"), _text_wp("<p>Browse our company policies below.</p>")
        ]),
        SPPage(title="Benefits", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Employee Benefits"), _text_wp("<p>Health, retirement, and wellbeing programmes.</p>")
        ]),
        SPPage(title="FAQ", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Frequently Asked Questions"), _text_wp("<p>Answers to the most common HR questions.</p>")
        ]),
    ]
    libraries = [
        DocumentLibrary(title="Policies", description="HR policy documents."),
        DocumentLibrary(title="Forms", description="HR forms and templates."),
        DocumentLibrary(title="Training Materials", description="Learning resources."),
    ]
    groups = [
        SharePointGroup(name="HR Admins", description="Full control", permission_level="Full Control"),
        SharePointGroup(name="HR Members", description="Edit access", permission_level="Edit"),
        SharePointGroup(name="All Employees", description="Read access", permission_level="Read"),
    ]
    return ProvisioningBlueprint(
        reasoning="HR Intranet template: communication site with welcome pages, policy libraries, and permission groups.",
        sites=[site],
        pages=pages,
        document_libraries=libraries,
        groups=groups,
    )


def _project_workspace_blueprint() -> ProvisioningBlueprint:
    from src.domain.entities.document import DocumentLibrary
    from src.domain.entities.security import SharePointGroup

    site = SPSite(
        title="Project Workspace",
        description="Collaborative project hub for the team.",
        name="project-workspace",
        template="sts",
        action=ActionType.CREATE,
    )
    pages = [
        SPPage(title="Project Charter", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Project Charter"), _text_wp("<p>Project scope, goals, and stakeholders.</p>")
        ]),
        SPPage(title="Status", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Project Status"), _text_wp("<p>Latest milestones and progress updates.</p>")
        ]),
        SPPage(title="Resources", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Project Resources"), _text_wp("<p>Links, tools, and reference materials.</p>")
        ]),
    ]
    libraries = [
        DocumentLibrary(title="Project Documents", description="All project files."),
        DocumentLibrary(title="Deliverables", description="Final outputs and reports."),
    ]
    groups = [
        SharePointGroup(name="Project Managers", description="Full control", permission_level="Full Control"),
        SharePointGroup(name="Project Members", description="Edit access", permission_level="Edit"),
        SharePointGroup(name="Stakeholders", description="Read-only", permission_level="Read"),
    ]
    return ProvisioningBlueprint(
        reasoning="Project Workspace template: team site with charter/status/resources pages and permission groups.",
        sites=[site],
        pages=pages,
        document_libraries=libraries,
        groups=groups,
    )


def _department_portal_blueprint() -> ProvisioningBlueprint:
    from src.domain.entities.document import DocumentLibrary
    from src.domain.entities.security import SharePointGroup

    site = SPSite(
        title="Department Portal",
        description="Departmental information and resources.",
        name="department-portal",
        template="sitepagepublishing",
        action=ActionType.CREATE,
    )
    pages = [
        SPPage(title="Home", layout="home", action=ActionType.CREATE, webparts=[
            _welcome_wp("Welcome to the Department"), _text_wp("<p>News, resources, and team updates.</p>")
        ]),
        SPPage(title="News", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Department News"),
            WebPart(type="News", properties={}, webpart_type="News"),
        ]),
        SPPage(title="Team", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Our Team"),
            WebPart(type="People", properties={"personas": []}, webpart_type="People"),
        ]),
    ]
    libraries = [
        DocumentLibrary(title="Resources", description="Department resources and guides."),
    ]
    groups = [
        SharePointGroup(name="Department Owners", description="Full control", permission_level="Full Control"),
        SharePointGroup(name="Department Members", description="Edit", permission_level="Edit"),
        SharePointGroup(name="Visitors", description="Read", permission_level="Read"),
    ]
    return ProvisioningBlueprint(
        reasoning="Department Portal template: communication site with home/news/team pages.",
        sites=[site],
        pages=pages,
        document_libraries=libraries,
        groups=groups,
    )


def _marketing_hub_blueprint() -> ProvisioningBlueprint:
    from src.domain.entities.document import DocumentLibrary
    from src.domain.entities.security import SharePointGroup

    site = SPSite(
        title="Marketing Hub",
        description="Marketing campaigns, brand assets, and content.",
        name="marketing-hub",
        template="sitepagepublishing",
        action=ActionType.CREATE,
    )
    pages = [
        SPPage(title="Home", layout="home", action=ActionType.CREATE, webparts=[
            _welcome_wp("Marketing Hub"),
            _text_wp("<p>Campaigns, brand guidelines, and upcoming events.</p>"),
        ]),
        SPPage(title="Campaigns", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Active Campaigns"), _text_wp("<p>Track and manage ongoing campaigns.</p>")
        ]),
        SPPage(title="Brand Guidelines", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Brand Guidelines"), _text_wp("<p>Logos, colours, typography, and tone of voice.</p>")
        ]),
        SPPage(title="Events", layout="article", action=ActionType.CREATE, webparts=[
            _welcome_wp("Upcoming Events"),
            WebPart(type="Events", properties={}, webpart_type="Events"),
        ]),
    ]
    libraries = [
        DocumentLibrary(title="Brand Assets", description="Logos, images, and brand materials."),
        DocumentLibrary(title="Campaign Materials", description="Campaign briefs, copy, and creative."),
    ]
    groups = [
        SharePointGroup(name="Marketing Team", description="Full control", permission_level="Full Control"),
        SharePointGroup(name="Content Contributors", description="Edit", permission_level="Edit"),
        SharePointGroup(name="Company", description="Read", permission_level="Read"),
    ]
    return ProvisioningBlueprint(
        reasoning="Marketing Hub template: communication site with campaigns, brand, and events pages.",
        sites=[site],
        pages=pages,
        document_libraries=libraries,
        groups=groups,
    )


# ---------------------------------------------------------------------------
# SiteTemplate dataclass
# ---------------------------------------------------------------------------

@dataclass
class SiteTemplate:
    """A named, keyword-matched site provisioning template."""
    name: str
    description: str
    keywords: List[str]
    _blueprint_factory: Callable[[], ProvisioningBlueprint] = field(repr=False)

    def build_blueprint(self) -> ProvisioningBlueprint:
        """Return a fresh ProvisioningBlueprint for this template."""
        return self._blueprint_factory()

    def preview_text(self) -> str:
        """Return a human-readable summary of what will be provisioned."""
        bp = self.build_blueprint()
        lines = [f"📋 **{self.name}** — {self.description}\n"]
        if bp.sites:
            lines.append("🌐 **Sites:**")
            for s in bp.sites:
                lines.append(f"  • {s.title} ({s.template})")
        if bp.pages:
            lines.append("📄 **Pages:**")
            for p in bp.pages:
                lines.append(f"  • {p.title}")
        if bp.document_libraries:
            lines.append("📚 **Document Libraries:**")
            for lib in bp.document_libraries:
                lines.append(f"  • {lib.title}")
        if bp.groups:
            lines.append("👥 **Permission Groups:**")
            for g in bp.groups:
                lines.append(f"  • {g.name} ({g.permission_level})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry of all built-in templates
# ---------------------------------------------------------------------------

BUILT_IN_TEMPLATES: List[SiteTemplate] = [
    SiteTemplate(
        name="HR Intranet",
        description="Communication site with HR pages, policy libraries, and permission groups.",
        keywords=["hr intranet", "hr portal", "human resources", "hr site", "hr workspace"],
        _blueprint_factory=_hr_intranet_blueprint,
    ),
    SiteTemplate(
        name="Project Workspace",
        description="Team site with project charter, status, and deliverable libraries.",
        keywords=["project workspace", "project site", "project hub", "project team", "project space"],
        _blueprint_factory=_project_workspace_blueprint,
    ),
    SiteTemplate(
        name="Department Portal",
        description="Communication site for a department with news, team, and resources.",
        keywords=["department portal", "department site", "dept portal", "department hub", "department intranet"],
        _blueprint_factory=_department_portal_blueprint,
    ),
    SiteTemplate(
        name="Marketing Hub",
        description="Communication site with campaign, brand, and events pages.",
        keywords=["marketing hub", "marketing site", "marketing portal", "marketing workspace", "marketing intranet"],
        _blueprint_factory=_marketing_hub_blueprint,
    ),
]
