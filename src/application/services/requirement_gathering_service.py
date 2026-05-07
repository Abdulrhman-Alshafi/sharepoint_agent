"""Service for managing multi-turn requirement gathering conversations."""

import uuid
import re
from typing import Optional, Dict, Any, List, Tuple
from src.domain.entities.conversation import (
    ConversationState,
    GatheringPhase,
    ResourceType,
    ResourceSpecification,
    Question,
)
from src.application.services.question_templates import QuestionTemplates
from src.infrastructure.repositories.conversation_state_repository import (
    ConversationStateRepository,
    get_conversation_repository,
)


class RequirementGatheringService:
    """Manages the flow of gathering requirements through multi-turn conversations."""

    def __init__(self, conversation_repo: Optional[ConversationStateRepository] = None):
        """Initialize requirement gathering service.
        
        Args:
            conversation_repo: Repository for storing conversation state (optional)
        """
        self.conversation_repo = conversation_repo or get_conversation_repository()

    def detect_resource_intent(self, message: str) -> Optional[ResourceType]:
        """Detect what type of resource the user wants to create.
        
        Args:
            message: User's message
            
        Returns:
            ResourceType if detected, None otherwise
        """
        from src.detection.routing.resource_type_router import route_resource_type
        result = route_resource_type(message)
        if not result:
            return None
        _map = {
            "SITE": ResourceType.SITE,
            "PAGE": ResourceType.PAGE,
            "LIBRARY": ResourceType.LIBRARY,
            "LIST": ResourceType.LIST,
            "GROUP": ResourceType.GROUP,
            "VIEW": ResourceType.VIEW,
            "CONTENT_TYPE": ResourceType.CONTENT_TYPE,
        }
        return _map.get(result.intent)

    def start_gathering(self, session_id: str, message: str, resource_type: ResourceType) -> Tuple[ConversationState, Question]:
        """Start a new requirement gathering conversation.
        
        Args:
            session_id: Unique session identifier
            message: Original user message
            resource_type: Type of resource to gather requirements for
            
        Returns:
            Tuple of (ConversationState, first Question)
        """
        # Create resource spec
        required_fields = QuestionTemplates.get_required_fields(resource_type)
        spec = ResourceSpecification(
            resource_type=resource_type,
            required_fields=required_fields
        )
        
        # Extract any pre-provided information from the original message
        pre_extracted_data = self._extract_from_prompt(message, resource_type)
        spec.collected_fields.update(pre_extracted_data)
        
        # Create conversation state
        state = ConversationState(
            session_id=session_id,
            phase=GatheringPhase.GATHERING_DETAILS,
            resource_specs=[spec],
            current_question_index=0,
            current_resource_index=0,
            original_prompt=message
        )
        
        # Find the first unanswered question
        questions = QuestionTemplates.get_questions(resource_type)
        starting_index = 0
        for i, question in enumerate(questions):
            if question.field_name not in spec.collected_fields:
                starting_index = i
                break
        
        state.current_question_index = starting_index
        
        # Save state
        self.conversation_repo.save(state)
        
        # Return first unanswered question
        if starting_index < len(questions):
            return state, questions[starting_index]
        
        # All questions already answered - go to confirmation
        state.phase = GatheringPhase.CONFIRMATION
        self.conversation_repo.save(state)
        return state, None

    def process_answer(
        self,
        session_id: str,
        answer: str
    ) -> Tuple[ConversationState, Optional[Question], bool]:
        """Process user's answer to a question.
        
        Args:
            session_id: Unique session identifier
            answer: User's answer
            
        Returns:
            Tuple of (updated ConversationState, next Question or None, is_complete)
        """
        # Get state
        state = self.conversation_repo.get(session_id)
        if not state:
            raise ValueError(f"No active conversation found for session {session_id}")
        
        # Get current spec and questions
        spec = state.get_current_spec()
        if not spec:
            raise ValueError("No active resource specification")
        
        questions = QuestionTemplates.get_questions(spec.resource_type)
        current_question = questions[state.current_question_index]
        
        # Parse and store answer
        parsed_answer = self._parse_answer(answer, current_question)
        spec.collected_fields[current_question.field_name] = parsed_answer
        
        # Move to next question
        state.current_question_index += 1
        
        # Check if complete
        if state.current_question_index >= len(questions):
            state.phase = GatheringPhase.CONFIRMATION
            self.conversation_repo.save(state)
            return state, None, True
        
        # Skip optional questions based on previous answers
        while state.current_question_index < len(questions):
            next_question = questions[state.current_question_index]
            if not next_question.required and self._should_skip_question(next_question, spec):
                if next_question.default_value is not None:
                    spec.collected_fields[next_question.field_name] = next_question.default_value
                state.current_question_index += 1
            else:
                break
                
        # Check if complete again after skipping
        if state.current_question_index >= len(questions):
            state.phase = GatheringPhase.CONFIRMATION
            self.conversation_repo.save(state)
            return state, None, True
            
        next_question = questions[state.current_question_index]
        
        self.conversation_repo.save(state)
        return state, next_question, False

    def get_specification_summary(self,session_id: str) -> Dict[str, Any]:
        """Get a summary of collected specifications.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Summary dictionary
        """
        state = self.conversation_repo.get(session_id)
        if not state:
            return {}
        
        spec = state.get_current_spec()
        if not spec:
            return {}
        
        return {
            "resource_type": spec.resource_type.value,
            "completion": f"{spec.get_completion_percentage()}%",
            "collected_fields": spec.collected_fields,
            "ready_to_provision": spec.is_complete()
        }

    def confirm_and_complete(self, session_id: str) -> ConversationState:
        """Mark conversation as complete and ready for provisioning.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Final ConversationState
        """
        state = self.conversation_repo.get(session_id)
        if not state:
            raise ValueError(f"No active conversation found for session {session_id}")
        
        state.phase = GatheringPhase.COMPLETE
        self.conversation_repo.save(state)
        return state

    def cancel_gathering(self, session_id: str) -> bool:
        """Cancel an active gathering conversation.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if cancelled successfully
        """
        return self.conversation_repo.delete(session_id)

    def _extract_from_prompt(self, message: str, resource_type: ResourceType) -> Dict[str, Any]:
        """Extract pre-provided information from user's original prompt.
        
        Args:
            message: Original user message
            resource_type: Type of resource being created
            
        Returns:
            Dictionary of extracted field values
        """
        extracted = {}
        message_lower = message.lower()
        
        # Specific extraction for VIEW target list
        if resource_type == ResourceType.VIEW:
            target_list_patterns = [
                r"(?:for|on|in)\s+(?:the\s+)?['\"]?([A-Za-z][A-Za-z0-9\s]*?)['\"]?(?:\s+list|\s*$|\.|\,)",
                r"(?:for|on|in)\s+(?:the\s+)?['\"]([^'\"]+)['\"]"
            ]
            for pattern in target_list_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    t_list = match.group(1).strip()
                    # filter stop words
                    if t_list.lower().endswith(" list"):
                        t_list = t_list[:-5].strip()
                    extracted["target_list"] = t_list
                    break

        # Extract name/title from common patterns
        # Patterns: "called 'X'", "named 'X'", "called X", "named X"
        # Also: "create X list", "create a X library", etc.
        
        # Try quoted patterns first (most explicit)
        quoted_patterns = [
            r"(?:called|named|titled?)\s+['\"]([^'\"]+)['\"]",
            r"['\"]([^'\"]+)['\"]",  # Fallback to any quoted text
        ]
        
        for pattern in quoted_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                extracted_name = match.group(1).strip()
                # Filter out common stop words that might be falsely captured
                if extracted_name and len(extracted_name) > 2 and extracted_name.lower() not in ["list", "library", "page", "group", "view", "a", "an", "the"]:
                    extracted["title"] = extracted_name
                    break
        
        # If no quoted pattern found, try unquoted patterns
        if "title" not in extracted:
            unquoted_patterns = [
                # "called/named/name X list"
                r"(?:called|named|name)\s+([A-Za-z0-9][A-Za-z0-9\s\-_]+?)(?:\s+(?:list|library|page|group|view|site)|\.|$)",
                # "create a Project Tracker list"
                r"create\s+(?:a|an)?\s+([A-Za-z][A-Za-z0-9\s]+?)\s+(?:list|library|page|group|view|site)",
            ]
            
            if resource_type not in [ResourceType.VIEW, ResourceType.GROUP]:
                # "create new list for Salaries" - most specific first
                unquoted_patterns.insert(0, r"create\s+(?:a|an|new)?\s*(?:list|library|page|group|view)?\s+(?:for|about|on)\s+([A-Za-z][A-Za-z0-9\s]*?)(?:\s|$|\.|,)")
                # "for Salaries" as fallback
                unquoted_patterns.append(r"(?:for|about)\s+([A-Za-z][A-Za-z0-9\s]+?)(?:\s|$|\.|,)")
            
            for pattern in unquoted_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    extracted_name = match.group(1).strip()
                    # Filter out common stop words
                    stop_words = ["list", "library", "page", "group", "view", "site", "a", "an", "the", "new", "create", "team", "communication", "view for"]
                    if extracted_name and len(extracted_name) > 2 and extracted_name.lower() not in stop_words and not extracted_name.lower().startswith("view for"):
                        # Capitalize first letter for consistency
                        extracted["title"] = extracted_name.capitalize() if not extracted_name[0].isupper() else extracted_name
                        break
        
        # Extract description if provided
        description_patterns = [
            r"(?:description|purpose|for|to)\s+[:\-]?\s*['\"]([^'\"]+)['\"]",
            r"(?:this will|it will|should)\s+([^.]+?)(?:\.|$)",
        ]
        
        for pattern in description_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                desc = match.group(1).strip()
                if desc and len(desc) > 10:  # Meaningful description
                    extracted["description"] = desc
                    break
        
        # Extract columns for lists (patterns like "with columns X, Y, Z")
        if resource_type == ResourceType.LIST:
            # Check if user wants AI to generate columns
            ai_generate_patterns = [
                r"(?:you|ai|system)\s+(?:make|generate|create|add|decide)\s+(?:the\s+)?columns",
                r"generate\s+(?:suitable|appropriate|relevant)\s+columns",
                r"(?:use|add)\s+(?:default|standard|typical)\s+columns",
                r"you\s+(?:add|decide|choose|pick|select)\s+(?:the\s+)?(?:columns?|fields?)",
                r"(?:add|decide|choose)\s+(?:them|the\s+columns?)",
            ]
            
            for pattern in ai_generate_patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    extracted["columns"] = "AI_GENERATED"  # Marker to indicate AI should generate
                    break
            
            # If not AI-generated, look for explicit column list
            if "columns" not in extracted:
                columns_patterns = [
                    r"(?:with|having|include|includes)\s+(?:columns?|fields?)[:\-]?\s+([^.]+?)(?:\.|$)",
                    r"columns?\s+(?:for|like|such as|including)[:\-]?\s+([^.]+?)(?:\.|$)",
                ]
                
                for pattern in columns_patterns:
                    match = re.search(pattern, message, re.IGNORECASE)
                    if match:
                        columns_text = match.group(1).strip()
                        # Clean up common wrappers
                        columns_text = re.sub(r"^['\"]|['\"]$", "", columns_text)
                        if columns_text and not any(word in columns_text.lower() for word in ["make", "generate", "create", "you"]):
                            extracted["columns"] = columns_text
                            break
        
        # Extract page-specific fields
        if resource_type == ResourceType.PAGE:
            # Detect content type from keywords
            content_type_map = {
                "dashboard": "Dashboard with charts",
                "chart": "Dashboard with charts",
                "report": "Dashboard with charts",
                "link": "List of links",
                "gallery": "Image gallery",
                "news": "News and announcements",
                "announcement": "News and announcements",
                "team": "Team overview",
                "member": "Team overview",
            }
            for keyword, ctype in content_type_map.items():
                if keyword in message_lower:
                    extracted["content_type"] = ctype
                    break
            
            # Detect section preferences from keywords
            section_keywords = {
                "hero": "Hero banner",
                "quick link": "Quick links",
                "news feed": "News feed",
                "people": "People",
                "text": "Text content",
            }
            detected_sections = [label for kw, label in section_keywords.items() if kw in message_lower]
            if detected_sections:
                extracted["sections"] = ", ".join(detected_sections)
            
            # Detect AI content generation preference
            if any(phrase in message_lower for phrase in ["generate content", "ai content", "write content"]):
                extracted["main_content"] = "Generate it for me"
        
        # Extract site child resource preference
        if resource_type == ResourceType.SITE:
            if any(phrase in message_lower for phrase in ["with pages", "with lists", "with libraries", "include pages"]):
                # User mentioned child resources — leave site_content for them to specify
                pass
            elif any(phrase in message_lower for phrase in ["no pages", "no lists", "only the site", "just the site"]):
                extracted["site_content"] = "Just the site, no extras"

        # Extract boolean preferences (sample data, permissions, etc.)
        if "sample data" in message_lower or "add sample" in message_lower or "seed" in message_lower:
            extracted["add_sample_data"] = "Yes, add sample data"

        # Extract library folder preferences
        if resource_type == ResourceType.LIBRARY:
            if any(p in message_lower for p in ["with folder", "with folders", "create folders", "add folders", "include folders"]):
                extracted["create_folders"] = "Yes, create folders now"
                folder_match = re.search(r"(?:folders?|folder structure)\s*[:\-]?\s*(.+)$", message, re.IGNORECASE)
                if folder_match and folder_match.group(1).strip():
                    extracted["folder_paths"] = folder_match.group(1).strip()
            elif any(p in message_lower for p in ["no folder", "without folder", "skip folders"]):
                extracted["create_folders"] = "No folders for now"
        
        return extracted

    def _parse_answer(self, answer: str, question: Question) -> Any:
        """Parse user's answer based on question type.
        
        Args:
            answer: User's answer string
            question: The question being answered
            
        Returns:
            Parsed answer value
        """
        answer = answer.strip()

        # Handle "you decide" / "you add them" style answers for the columns field
        if question.field_name == "columns":
            ai_decide_phrases = [
                "you decide", "you add", "you add them", "you choose", "you pick",
                "you generate", "you create", "ai decide", "auto", "automatic",
                "generate them", "decide for me", "you select",
            ]
            if any(phrase in answer.lower() for phrase in ai_decide_phrases):
                return "AI_GENERATED"

        if question.field_name == "folder_paths":
            answer_lower = answer.lower()
            if answer_lower in {"skip folders", "skip", "none", "no", "n/a"}:
                return []
            parts = re.split(r"[\n,;]+", answer)
            normalized = []
            for p in parts:
                folder = p.strip().lstrip("-*")
                if folder:
                    normalized.append(folder)
            return normalized
        
        if question.field_type == "boolean":
            return answer.lower() in ["yes", "y", "true", "1", "sure", "ok", "yeah"]
        
        elif question.field_type == "number":
            try:
                return int(answer)
            except ValueError:
                return question.default_value or 0
        
        elif question.field_type == "choice":
            # Try to match to one of the options
            answer_lower = answer.lower()
            for option in question.options:
                if answer_lower in option.lower() or option.lower() in answer_lower:
                    return option
            # Default to first option or answer as-is
            return question.options[0] if question.options else answer
        
        else:  # text and multi_choice
            # For title/name fields, try to extract just the name when the user gives a
            # descriptive answer (e.g. "it is a list for xyz" → "xyz").
            if question.field_name in ("title", "name"):
                clean = self._extract_name_from_answer(answer)
                if clean:
                    return clean
            return answer

    def _extract_name_from_answer(self, answer: str) -> Optional[str]:
        """Attempt to extract a clean name/title from a descriptive answer.

        Returns the extracted name when the answer looks like a description
        (e.g. "it is a list for xyz", "this list is for tracking xyz"),
        or None when the answer already looks like a plain name.
        """
        answer_stripped = answer.strip()
        # If the answer has no spaces it is already a plain name – leave it.
        # Also leave it when it is very short (≤ 4 words) and does not contain
        # descriptive lead-in phrases.
        LEAD_IN_PHRASES = (
            "it is", "it's", "this is", "this will", "this list",
            "it will be", "this is a", "it is a",
        )
        answer_lower = answer_stripped.lower()
        has_lead_in = any(answer_lower.startswith(p) for p in LEAD_IN_PHRASES)
        if not has_lead_in and len(answer_stripped.split()) <= 4:
            # Looks like the user typed a plain name directly – return None so the
            # raw answer is used unchanged.
            return None

        # Try to pull out the name from common descriptive patterns.
        name_patterns = [
            # "called/named 'X'" or "called/named X"
            r"(?:called|named|titled?)\s+['\"]([^'\"]+)['\"]",
            r"(?:called|named|titled?)\s+([A-Za-z][A-Za-z0-9 ]+?)(?:\s+(?:list|library|page|group|view|site)|[.,]|$)",
            # "it is a list for/called/named X"
            r"(?:it(?:'s| is)?\s+(?:a |an |the )?(?:list|library|page)?\s*(?:for|called|named|about))\s+([A-Za-z][A-Za-z0-9 ]+?)(?:[.,]|$)",
            # "this list is for/about X"
            r"(?:this\s+(?:list|library|page)\s+(?:is\s+)?(?:for|about|called|named))\s+([A-Za-z][A-Za-z0-9 ]+?)(?:[.,]|$)",
            # general "for/about X" fallback
            r"(?:for|about)\s+([A-Za-z][A-Za-z0-9 ]+?)(?:\s+(?:list|library|page)|[.,]|$)",
        ]
        stop_words = {"list", "library", "page", "group", "view", "site", "a", "an", "the"}
        for pattern in name_patterns:
            match = re.search(pattern, answer_stripped, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if candidate and len(candidate) > 1 and candidate.lower() not in stop_words:
                    # Preserve original capitalisation; only capitalise the first letter
                    # when the candidate is all-lowercase.
                    if candidate.islower():
                        candidate = candidate.capitalize()
                    return candidate
        return None

    def _should_skip_question(self, question: Question, spec: ResourceSpecification) -> bool:
        """Determine if a question should be auto-skipped based on previous answers.
        
        Args:
            question: Question to potentially skip
            spec: Current resource specification
            
        Returns:
            True if should skip
        """
        # Skip permission-related questions if "No restrictions" was selected
        if spec.resource_type == ResourceType.LIBRARY:
            if question.field_name == "permission_groups":
                needs_permissions = spec.collected_fields.get("needs_permissions", "")
                if "No" in needs_permissions or "everyone" in needs_permissions.lower():
                    return True
            if question.field_name == "folder_paths":
                create_folders = str(spec.collected_fields.get("create_folders", "")).lower()
                if "no folders" in create_folders:
                    return True
        
        return False
