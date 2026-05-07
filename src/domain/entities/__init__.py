"""Domain entities - split into focused modules for better organization."""

# Core entities
from src.domain.entities.core import (
    ActionType,
    SPSite,
    SPList,
    SPPage,
    CustomWebPartCode,
    ProvisioningBlueprint,
)

# Document library
from src.domain.entities.document import DocumentLibrary, LibraryItem

# Security
from src.domain.entities.security import (
    PermissionLevel,
    SharePointGroup,
)

# Enterprise
from src.domain.entities.enterprise import (
    TermSet,
    ContentType,
    SPView,
    WorkflowScaffold,
)

# Query results
from src.domain.entities.query import (
    DataQueryResult,
    PromptValidationResult,
)

# Conversation and gathering
from src.domain.entities.conversation import (
    GatheringPhase,
    ResourceType,
    Question,
    ResourceSpecification,
    ConversationState,
    ConversationContext,
    ContentAnalysis,
    FieldSource,
)

# Preview and decisions
from src.domain.entities.preview import (
    OperationType,
    RiskLevel,
    WebPartType,
    ResourceChange,
    ProvisioningPreview,
    DeletionImpact,
    WebPartCapability,
    WebPartCatalogEntry,
    WebPartDecision,
    DryRunResult,
)


__all__ = [
    # Core
    "ActionType",
    "SPList",
    "SPPage",
    "CustomWebPartCode",
    "ProvisioningBlueprint",
    # Document
    "DocumentLibrary",
    "LibraryItem",
    # Security
    "PermissionLevel",
    "SharePointGroup",
    # Enterprise
    "TermSet",
    "ContentType",
    "SPView",
    "WorkflowScaffold",
    # Query
    "DataQueryResult",
    "PromptValidationResult",
    # Conversation
    "GatheringPhase",
    "ResourceType",
    "Question",
    "ResourceSpecification",
    "ConversationState",
    "ConversationContext",
    "ContentAnalysis",
    "FieldSource",
    # Preview and decisions
    "OperationType",
    "RiskLevel",
    "WebPartType",
    "ResourceChange",
    "ProvisioningPreview",
    "DeletionImpact",
    "WebPartCapability",
    "WebPartCatalogEntry",
    "WebPartDecision",
    "DryRunResult",
]
