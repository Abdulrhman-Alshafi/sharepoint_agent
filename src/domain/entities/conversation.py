"""Conversation and requirement gathering entities."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time


class GatheringPhase(str, Enum):
    """Phases of the requirement gathering process."""
    INTENT_DETECTED = "INTENT_DETECTED"  # User wants to create something
    GATHERING_DETAILS = "GATHERING_DETAILS"  # Asking questions to collect specs
    CONFIRMATION = "CONFIRMATION"  # Showing summary, asking for confirmation
    RISK_CONFIRMATION = "RISK_CONFIRMATION"  # Waiting for high-risk confirmation
    COMPLETE = "COMPLETE"  # User confirmed, ready to provision


class ResourceType(str, Enum):
    """Types of SharePoint resources we can gather requirements for."""
    SITE = "SITE"
    LIST = "LIST"
    PAGE = "PAGE"
    LIBRARY = "LIBRARY"
    GROUP = "GROUP"
    CONTENT_TYPE = "CONTENT_TYPE"
    TERM_SET = "TERM_SET"
    VIEW = "VIEW"


@dataclass
class Question:
    """A question to ask the user during requirement gathering."""
    field_name: str
    question_text: str
    field_type: str  # "text", "choice", "multi_choice", "number", "boolean"
    required: bool = True
    options: List[str] = field(default_factory=list)
    default_value: Optional[Any] = None
    validation_hint: str = ""


@dataclass
class ResourceSpecification:
    """Partial or complete specification for a SharePoint resource."""
    resource_type: ResourceType
    collected_fields: Dict[str, Any] = field(default_factory=dict)
    required_fields: List[str] = field(default_factory=list)
    
    def is_complete(self) -> bool:
        """Check if all required fields have been collected."""
        return all(
            field_name in self.collected_fields and self.collected_fields[field_name] is not None
            for field_name in self.required_fields
        )
    
    def get_completion_percentage(self) -> int:
        """Get percentage of required fields collected."""
        if not self.required_fields:
            return 100
        collected = sum(
            1 for field in self.required_fields
            if field in self.collected_fields and self.collected_fields[field] is not None
        )
        return int((collected / len(self.required_fields)) * 100)


@dataclass
class ConversationState:
    """Entity tracking the state of a multi-turn conversation."""
    session_id: str
    phase: GatheringPhase
    resource_specs: List[ResourceSpecification] = field(default_factory=list)
    current_question_index: int = 0
    current_resource_index: int = 0
    original_prompt: str = ""
    provisioning_prompt: str = ""  # Built prompt for provisioning (used for retry after risk confirmation)
    context_memory: Dict[str, Any] = field(default_factory=dict)  # Enhanced: stores extracted facts, confidence scores
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def get_current_spec(self) -> Optional[ResourceSpecification]:
        """Get the resource spec currently being gathered."""
        if 0 <= self.current_resource_index < len(self.resource_specs):
            return self.resource_specs[self.current_resource_index]
        return None
    
    def mark_updated(self) -> None:
        """Update the last modified timestamp."""
        self.updated_at = time.time()
    
    def is_expired(self, ttl_seconds: int = 1800) -> bool:
        """Check if conversation state has expired (default 30 minutes)."""
        return (time.time() - self.updated_at) > ttl_seconds

@dataclass
class ConversationContext:
    """Context memory for intelligent conversation tracking."""
    extracted_facts: Dict[str, Any] = field(default_factory=dict)  # Key: fact_name, Value: fact data
    confidence_scores: Dict[str, float] = field(default_factory=dict)  # Key: fact_name, Value: 0.0-1.0
    recent_resources: List[Dict[str, Any]] = field(default_factory=list)  # Recently created/accessed resources
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # Learned preferences
    vocabulary: Dict[str, str] = field(default_factory=dict)  # User's preferred terms
    
    def add_fact(self, name: str, value: Any, confidence: float, source: str = "inferred") -> None:
        """Add a fact to the context with confidence score."""
        self.extracted_facts[name] = {"value": value, "source": source, "timestamp": time.time()}
        self.confidence_scores[name] = min(1.0, max(0.0, confidence))  # Clamp to 0-1
    
    def get_fact(self, name: str) -> Optional[Any]:
        """Get a fact value if exists."""
        fact_data = self.extracted_facts.get(name)
        return fact_data["value"] if fact_data else None
    
    def has_confidence(self, name: str, min_confidence: float = 0.8) -> bool:
        """Check if a fact exists with minimum confidence."""
        return name in self.confidence_scores and self.confidence_scores[name] >= min_confidence
    
    def merge_facts(self, new_facts: Dict[str, Any], source: str = "user_stated") -> None:
        """Merge new facts with high confidence (1.0 for user-stated)."""
        confidence = 1.0 if source == "user_stated" else 0.7
        for name, value in new_facts.items():
            self.add_fact(name, value, confidence, source)
    
    def add_recent_resource(self, resource_type: str, resource_id: str, resource_name: str, metadata: Dict[str, Any] = None) -> None:
        """Track recently created/accessed resource."""
        resource_entry = {
            "type": resource_type,
            "id": resource_id,
            "name": resource_name,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        self.recent_resources.insert(0, resource_entry)  # Add to front
        # Keep only last 50
        self.recent_resources = self.recent_resources[:50]


@dataclass
class ContentAnalysis:
    """Analysis results for SharePoint content (sites, pages, lists)."""
    resource_type: str  # "site", "page", "list", "library"
    resource_id: str
    resource_name: str
    summary: str  # 2-3 sentence summary
    detailed_description: str  # Comprehensive explanation
    main_topics: List[str] = field(default_factory=list)  # Keywords/topics
    purpose: str = ""  # Inferred intent/goal
    audience: str = ""  # Inferred target users
    components: List[Dict[str, Any]] = field(default_factory=list)  # Web parts, sections, lists, etc.
    metadata: Dict[str, Any] = field(default_factory=dict)  # Creation date, owner, etc.
    suggested_actions: List[str] = field(default_factory=list)  # Smart follow-up actions
    confidence_score: float = 0.0  # 0.0-1.0 confidence in analysis
    analyzed_at: float = field(default_factory=time.time)


@dataclass  
class FieldSource:
    """Tracks where a specification field value came from."""
    field_name: str
    value: Any
    source: str  # "user_stated", "inferred", "default", "context"
    confidence: float  # 0.0-1.0
    
    def get_indicator(self) -> str:
        """Get display indicator for UI."""
        if self.source == "user_stated":
            return "✓"  # Explicitly stated
        elif self.source == "context":
            return "↻"  # From previous conversation
        elif self.source == "inferred":
            return "~"  # AI inferred
        else:
            return "*"  # Default value