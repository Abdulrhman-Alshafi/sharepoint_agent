"""Preview and decision-making entities for SharePoint operations."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time


class OperationType(str, Enum):
    """Type of operation being previewed."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class RiskLevel(str, Enum):
    """Risk assessment for operations."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class WebPartType(str, Enum):
    """Built-in or custom web part classification."""
    BUILTIN = "builtin"
    CUSTOM = "custom"


@dataclass
class ResourceChange:
    """Describes a change to a SharePoint resource."""
    resource_type: str  # "list", "page", "site", "library", "web_part"
    resource_name: str
    change_type: str  # "add", "remove", "modify"
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    description: str = ""  # Human-readable description of change


@dataclass
class ProvisioningPreview:
    """Preview of provisioning operation before execution."""
    operation_type: OperationType
    affected_resources: List[ResourceChange] = field(default_factory=list)
    visual_representation: str = ""  # Markdown/HTML showing layout
    risk_level: RiskLevel = RiskLevel.LOW
    warnings: List[str] = field(default_factory=list)
    estimated_duration_seconds: int = 30
    required_permissions: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    
    def add_change(self, change: ResourceChange) -> None:
        """Add a resource change to the preview."""
        self.affected_resources.append(change)
    
    def get_summary(self) -> str:
        """Get a text summary of the preview."""
        lines = [f"**Preview: {self.operation_type.value} Operation**\n"]
        
        if self.affected_resources:
            lines.append(f"**Affected Resources ({len(self.affected_resources)}):**")
            for change in self.affected_resources:
                icon = "✅" if change.change_type == "add" else "❌" if change.change_type == "remove" else "✏️"
                lines.append(f"{icon} {change.resource_type.upper()}: {change.resource_name}")
                if change.description:
                    lines.append(f"   → {change.description}")
        
        if self.visual_representation:
            lines.append(f"\n{self.visual_representation}")
        
        if self.warnings:
            lines.append("\n**⚠️ Warnings:**")
            for warning in self.warnings:
                lines.append(f"  - {warning}")
        
        lines.append(f"\n**Risk Level:** {self.risk_level.value} | **Duration:** ~{self.estimated_duration_seconds}s")
        
        return "\n".join(lines)


@dataclass
class DeletionImpact:
    """Analysis of impact when deleting a resource."""
    target_resource_type: str
    target_resource_id: str
    target_resource_name: str
    dependent_resources: List[Dict[str, Any]] = field(default_factory=list)  # Resources that reference this
    data_loss_summary: str = ""  # Description of data that will be lost
    item_count: int = 0  # Number of items/pages/files affected
    last_modified: Optional[str] = None  # ISO timestamp
    reversibility: str = "reversible"  # "reversible" (recycle bin) or "permanent"
    confirmation_required: bool = True
    risk_level: RiskLevel = RiskLevel.MEDIUM
    
    def get_impact_message(self) -> str:
        """Get formatted impact warning message."""
        lines = [f"⚠️ **Deleting '{self.target_resource_name}' ({self.target_resource_type})**\n"]
        
        if self.dependent_resources:
            lines.append(f"**This will affect {len(self.dependent_resources)} dependent resource(s):**")
            for dep in self.dependent_resources[:5]:  # Show max 5
                lines.append(f"  - {dep.get('name', 'Unknown')} ({dep.get('type', 'Unknown')})")
            if len(self.dependent_resources) > 5:
                lines.append(f"  - ... and {len(self.dependent_resources) - 5} more")
        
        if self.data_loss_summary:
            lines.append(f"\n**Data Loss:** {self.data_loss_summary}")
        
        if self.item_count > 0:
            lines.append(f"**Items affected:** {self.item_count}")
        
        if self.last_modified:
            lines.append(f"**Last modified:** {self.last_modified}")
        
        lines.append(f"\n**Reversibility:** {self.reversibility.upper()}")
        lines.append(f"**Risk Level:** {self.risk_level.value}")
        
        if self.confirmation_required:
            lines.append(f"\nTo confirm, type: **yes, delete {self.target_resource_name}**")
        
        return "\n".join(lines)


@dataclass
class WebPartCapability:
    """Describes a capability of a web part."""
    name: str
    description: str
    supports_data_source: bool = False
    supports_customization: bool = True
    use_cases: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)


@dataclass
class WebPartCatalogEntry:
    """Entry in the built-in web part catalog."""
    web_part_name: str
    web_part_type: str  # Internal type identifier
    category: str  # "content", "navigation", "data", "media", "social"
    capabilities: List[WebPartCapability] = field(default_factory=list)
    common_use_cases: List[str] = field(default_factory=list)
    
    def matches_requirement(self, requirement: str, threshold: float = 0.7) -> bool:
        """Check if this web part matches requirement (simple keyword matching)."""
        requirement_lower = requirement.lower()
        # Simple keyword matching - can be enhanced with AI later
        matches = any(
            use_case.lower() in requirement_lower or requirement_lower in use_case.lower()
            for use_case in self.common_use_cases
        )
        return matches


@dataclass
class WebPartDecision:
    """Decision on whether to use built-in or custom web part."""
    requirement: str  # What the user needs
    recommended_type: WebPartType
    builtin_option: Optional[WebPartCatalogEntry] = None
    custom_features_needed: List[str] = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0  # 0.0-1.0
    
    def get_explanation(self) -> str:
        """Get human-readable explanation of the decision."""
        if self.recommended_type == WebPartType.BUILTIN and self.builtin_option:
            return (
                f"**Recommendation:** Use built-in **{self.builtin_option.web_part_name}** web part\n\n"
                f"**Reason:** {self.reasoning}\n\n"
                f"This covers your requirement: '{self.requirement}'"
            )
        else:
            features_list = "\n".join(f"  - {feature}" for feature in self.custom_features_needed)
            return (
                f"**Recommendation:** Create custom SPFx web part\n\n"
                f"**Reason:** {self.reasoning}\n\n"
                f"**Custom features needed:**\n{features_list}\n\n"
                f"Your requirement: '{self.requirement}'"
            )


@dataclass
class DryRunResult:
    """Result of a dry-run operation (preview without execution)."""
    would_create: List[str] = field(default_factory=list)
    would_update: List[str] = field(default_factory=list)
    would_delete: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    estimated_duration_seconds: int = 0
    required_permissions: List[str] = field(default_factory=list)
    success: bool = True
    
    def get_summary(self) -> str:
        """Get formatted dry-run summary."""
        lines = ["**🔍 Dry-Run Results**\n"]
        
        if self.would_create:
            lines.append(f"**Would CREATE ({len(self.would_create)}):**")
            for item in self.would_create:
                lines.append(f"  ✅ {item}")
        
        if self.would_update:
            lines.append(f"\n**Would UPDATE ({len(self.would_update)}):**")
            for item in self.would_update:
                lines.append(f"  ✏️ {item}")
        
        if self.would_delete:
            lines.append(f"\n**Would DELETE ({len(self.would_delete)}):**")
            for item in self.would_delete:
                lines.append(f"  ❌ {item}")
        
        if self.validation_errors:
            lines.append("\n**❌ Validation Errors:**")
            for error in self.validation_errors:
                lines.append(f"  - {error}")
            self.success = False
        
        if self.validation_warnings:
            lines.append("\n**⚠️ Warnings:**")
            for warning in self.validation_warnings:
                lines.append(f"  - {warning}")
        
        lines.append(f"\n**Estimated Duration:** ~{self.estimated_duration_seconds}s")
        lines.append(f"**Status:** {'✅ Ready to execute' if self.success else '❌ Has errors'}")
        
        return "\n".join(lines)
