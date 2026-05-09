"""Smart question service with context awareness to avoid repetitive questions."""

from typing import Dict, Any, List, Optional
from src.domain.entities.conversation import ConversationContext, FieldSource, ResourceType
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.logging import get_logger
from pydantic import BaseModel, Field
import re

logger = get_logger(__name__)


class ExtractedFacts(BaseModel):
    """Pydantic model for AI-extracted facts from user message."""
    facts: Dict[str, Any] = Field(description="Dictionary of extracted facts with field names as keys")
    confidence_scores: Dict[str, float] = Field(description="Confidence score (0.0-1.0) for each fact")


class SmartQuestionService:
    """Service for intelligent question asking with context awareness."""
    
    def __init__(self):
        """Initialize smart question service."""
        self.confidence_threshold_skip = 0.8  # Skip questions with >0.8 confidence
        self.confidence_threshold_confirm = 0.5  # Confirm questions with 0.5-0.8 confidence
    
    async def extract_known_facts(self, message: str, resource_type: ResourceType, 
                                    context: Optional[ConversationContext] = None) -> Dict[str, FieldSource]:
        """Extract known facts from user message using AI.
        
        Args:
            message: User's message
            resource_type: Type of resource being created
            context: Optional conversation context
            
        Returns:
            Dictionary mapping field names to FieldSource objects
        """
        # Use AI to extract facts from message
        extracted = await self._ai_extract_facts(message, resource_type)
        
        field_sources = {}
        
        # Convert extracted facts to FieldSource objects
        for field_name, value in extracted.facts.items():
            confidence = extracted.confidence_scores.get(field_name, 0.7)
            field_sources[field_name] = FieldSource(
                field_name=field_name,
                value=value,
                source="user_stated" if confidence >= 0.9 else "inferred",
                confidence=confidence
            )
        
        # Merge with context if available
        if context:
            for field_name, fact_data in context.extracted_facts.items():
                if field_name not in field_sources:
                    field_sources[field_name] = FieldSource(
                        field_name=field_name,
                        value=fact_data.get("value"),
                        source="context",
                        confidence=context.confidence_scores.get(field_name, 0.6)
                    )
        
        return field_sources
    
    def determine_missing_fields(self, resource_type: ResourceType, known_fields: Dict[str, FieldSource], 
                                  required_fields: List[str]) -> List[str]:
        """Determine which required fields are still missing.
        
        Args:
            resource_type: Type of resource
            known_fields: Dictionary of known field sources
            required_fields: List of required field names
            
        Returns:
            List of missing field names that need to be asked
        """
        missing = []
        
        for field_name in required_fields:
            if field_name not in known_fields:
                # Completely missing
                missing.append(field_name)
            elif known_fields[field_name].confidence < self.confidence_threshold_skip:
                # Low confidence, should ask or confirm
                if known_fields[field_name].confidence < self.confidence_threshold_confirm:
                    missing.append(field_name)
        
        return missing
    
    def should_skip_question(self, field_name: str, known_fields: Dict[str, FieldSource]) -> bool:
        """Determine if a question should be skipped based on context.
        
        Args:
            field_name: Field name to check
            known_fields: Dictionary of known field sources
            
        Returns:
            True if question should be skipped (field already known with high confidence)
        """
        if field_name not in known_fields:
            return False
        
        field_source = known_fields[field_name]
        return field_source.confidence >= self.confidence_threshold_skip
    
    def should_confirm_question(self, field_name: str, known_fields: Dict[str, FieldSource]) -> bool:
        """Determine if a question should be asked as confirmation (already have medium confidence value).
        
        Args:
            field_name: Field name to check
            known_fields: Dictionary of known field sources
            
        Returns:
            True if should ask as confirmation
        """
        if field_name not in known_fields:
            return False
        
        field_source = known_fields[field_name]
        return (self.confidence_threshold_confirm <= field_source.confidence < self.confidence_threshold_skip)
    
    def generate_confirmation_message(self, auto_filled_fields: Dict[str, FieldSource]) -> str:
        """Generate a message showing what fields were auto-filled.
        
        Args:
            auto_filled_fields: Dictionary of auto-filled fields
            
        Returns:
            Human-readable confirmation message
        """
        if not auto_filled_fields:
            return ""
        
        lines = ["**Auto-filled fields based on your request:**\n"]
        
        for field_name, field_source in auto_filled_fields.items():
            indicator = field_source.get_indicator()
            value_str = str(field_source.value)
            if len(value_str) > 50:
                value_str = value_str[:47] + "..."
            
            source_desc = {
                "user_stated": "you stated",
                "inferred": "inferred",
                "context": "from previous conversation",
                "default": "default value"
            }.get(field_source.source, "auto-filled")
            
            lines.append(f"{indicator} **{field_name}**: {value_str} ({source_desc})")
        
        lines.append("\nProceed with these values or let me know if you'd like to change anything.")
        
        return "\n".join(lines)
    
    async def _ai_extract_facts(self, message: str, resource_type: ResourceType) -> ExtractedFacts:
        """Use AI to extract facts from user message.
        
        Args:
            message: User's message
            resource_type: Type of resource
            
        Returns:
            ExtractedFacts with field values and confidence scores
        """
        try:
            client, model = get_instructor_client()
            
            resource_fields = self._get_resource_fields(resource_type)
            
            prompt = f"""Extract factual information from this user message for creating a SharePoint {resource_type.value}.

User message: "{message}"

Possible fields to extract: {', '.join(resource_fields)}

For each field you can extract:
1. Provide the extracted value
2. Provide a confidence score (0.0-1.0)
   - 1.0: User explicitly stated it (e.g., "create a list named Tasks")
   - 0.7-0.9: Strongly implied or inferred from context
   - 0.4-0.6: Weakly inferred, might need confirmation
   - <0.4: Very uncertain

Only extract fields that are mentioned or can be reasonably inferred. Do not make things up.

Examples:
- "Create an HR site called Employee Hub" → title="Employee Hub" (1.0), purpose="HR" (0.8)
- "Make a list for tracking bugs" → title="Bugs" (0.7), purpose="bug tracking" (0.9)
- "Add a page with announcements" → title="Announcements" (0.7), content_type="announcements" (0.9)
"""

            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert at extracting structured information from natural language requests."},
                    {"role": "user", "content": prompt}
                ],
                response_model=ExtractedFacts,
                max_retries=2
            )
            
            return response
        
        except Exception as e:
            logger.warning("AI extraction failed: %s", e)
            # Fallback to simple regex extraction
            return self._fallback_extract_facts(message, resource_type)
    
    def _fallback_extract_facts(self, message: str, resource_type: ResourceType) -> ExtractedFacts:
        """Fallback fact extraction using simple patterns.
        
        Args:
            message: User's message
            resource_type: Type of resource
            
        Returns:
            ExtractedFacts with simple pattern matching
        """
        facts = {}
        confidence_scores = {}
        
        # Extract title/name patterns
        title_patterns = [
            r'(?:named|called)\s+["\']([^"\']+)["\']',
            r'(?:named|called)\s+(\w+(?:\s+\w+)*)',
            r'create\s+(?:a|an)\s+["\']([^"\']+)["\']',
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                facts["title"] = match.group(1).strip()
                confidence_scores["title"] = 0.9
                break
        
        # Extract purpose from context words
        if "HR" in message or "human resources" in message.lower():
            facts["purpose"] = "HR"
            confidence_scores["purpose"] = 0.8
        elif "finance" in message.lower() or "budget" in message.lower():
            facts["purpose"] = "Finance"
            confidence_scores["purpose"] = 0.8
        elif "IT" in message or "technology" in message.lower():
            facts["purpose"] = "IT"
            confidence_scores["purpose"] = 0.8
        
        return ExtractedFacts(facts=facts, confidence_scores=confidence_scores)
    
    def _get_resource_fields(self, resource_type: ResourceType) -> List[str]:
        """Get list of possible fields for a resource type.
        
        Args:
            resource_type: Type of resource
            
        Returns:
            List of field names
        """
        field_map = {
            ResourceType.LIST: ["title", "description", "columns", "column_types", "add_sample_data"],
            ResourceType.PAGE: ["title", "content_type", "main_content"],
            ResourceType.LIBRARY: ["title", "description", "create_folders", "folder_paths"],
            ResourceType.GROUP: ["name", "permission_level", "target_resource"],
            ResourceType.CONTENT_TYPE: ["name", "description", "columns"],
            ResourceType.TERM_SET: ["name", "terms"],
            ResourceType.VIEW: ["name", "list_name", "columns_to_show"],
        }
        
        return field_map.get(resource_type, ["title", "description"])
