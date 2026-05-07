"""Query intelligence utilities for smart filtering and classification."""

from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ResourceTypeDetector:
    """Detects and classifies SharePoint resource types."""
    
    @staticmethod
    def is_document_library(list_data: Dict[str, Any]) -> bool:
        """Determine if a list is actually a document library.
        
        SharePoint libraries are special types of lists with specific templates.
        
        Args:
            list_data: List metadata from Graph API
            
        Returns:
            True if the list is a document library
        """
        # Check template property only — Graph API returns 'documentLibrary' for all document libraries.
        # Do NOT use name-based heuristics as lists like 'HRDocuments' or 'Project Documents'
        # are regular lists, not document libraries.
        list_template = list_data.get("list", {}).get("template", "")
        return list_template == "documentLibrary"
    
    @staticmethod
    def classify_lists_by_type(all_lists: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Classify lists into libraries and regular lists.
        
        Args:
            all_lists: All lists from SharePoint
            
        Returns:
            Dictionary with 'libraries' and 'lists' keys
        """
        libraries = []
        lists = []
        
        for lst in all_lists:
            if ResourceTypeDetector.is_document_library(lst):
                libraries.append(lst)
            else:
                lists.append(lst)
        
        return {
            "libraries": libraries,
            "lists": lists
        }


class KeywordFilter:
    """Filters SharePoint resources by keywords."""
    
    # Semantic keyword expansion map
    KEYWORD_EXPANSIONS = {
        "hr": ["hr", "human resources", "employee", "personnel", "staff", "hiring", "payroll", "benefits"],
        "project": ["project", "task", "milestone", "deliverable", "sprint", "backlog"],
        "finance": ["finance", "financial", "budget", "accounting", "expense", "invoice", "payment", "money", "cost"],
        "money": ["money", "finance", "financial", "budget", "accounting", "expense", "invoice", "payment", "cost", "revenue", "income"],
        "it": ["it", "information technology", "tech", "software", "hardware", "system"],
        "sales": ["sales", "customer", "deal", "opportunity", "lead", "crm"],
        "marketing": ["marketing", "campaign", "brand", "social", "content", "promotion"],
        "kudos": ["kudos", "recognition", "appreciation", "likes", "comment", "post"],
        "poll": ["poll", "survey", "vote", "question", "feedback"],
    }
    
    @staticmethod
    def expand_keywords(keywords: List[str]) -> List[str]:
        """Expand keywords with semantic alternatives.
        
        Args:
            keywords: Original keywords
            
        Returns:
            Expanded list including semantic alternatives
        """
        expanded = set()
        for keyword in keywords:
            keyword_lower = keyword.lower()
            expanded.add(keyword_lower)
            
            # Check if this keyword has expansions
            if keyword_lower in KeywordFilter.KEYWORD_EXPANSIONS:
                expanded.update(KeywordFilter.KEYWORD_EXPANSIONS[keyword_lower])
        
        return list(expanded)
    
    @staticmethod
    def matches_keywords(text: str, keywords: List[str]) -> bool:
        """Check if text matches any of the keywords.
        
        Args:
            text: Text to check
            keywords: Keywords to match against
            
        Returns:
            True if any keyword is found in text
        """
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in keywords)
    
    @staticmethod
    def filter_by_keywords(
        resources: List[Dict[str, Any]], 
        keywords: List[str],
        expand_semantic: bool = True
    ) -> List[Dict[str, Any]]:
        """Filter resources by keywords in name and description.
        
        Args:
            resources: List of SharePoint resources
            keywords: Keywords to filter by
            expand_semantic: Whether to expand keywords semantically
            
        Returns:
            Filtered list of resources
        """
        if not keywords:
            return resources
        
        # Expand keywords if requested
        search_keywords = KeywordFilter.expand_keywords(keywords) if expand_semantic else keywords
        
        filtered = []
        for resource in resources:
            name = resource.get("displayName", "") or resource.get("name", "")
            description = resource.get("description", "")
            
            # Check if name or description matches any keyword
            if KeywordFilter.matches_keywords(name, search_keywords) or \
               KeywordFilter.matches_keywords(description, search_keywords):
                filtered.append(resource)
        
        return filtered


class QueryAnalyzer:
    """Analyzes queries to extract metadata and intent details."""

    @staticmethod
    def extract_count_target(question: str) -> Optional[str]:
        """Extract what to count from a question."""
        from src.detection.matching.query_classifier import classify_query_type
        result = classify_query_type(question)
        if not result or result.intent != "count":
            return None
        question_lower = question.lower()
        if "page" in question_lower:
            return "pages"
        elif "librar" in question_lower:
            return "libraries"
        elif "list" in question_lower:
            return "lists"
        elif "item" in question_lower:
            return "items"
        return None
        
        # Extract what to count
        if "page" in question_lower:
            return "pages"
        elif "librar" in question_lower:
            return "libraries"
        elif "list" in question_lower:
            return "lists"
        elif "item" in question_lower:
            return "items"
        
        return None
    
    @staticmethod
    def is_filtered_meta_query(question: str) -> Tuple[bool, Optional[str]]:
        """Check if question asks for filtered list of resources.
        
        Args:
            question: User question
            
        Returns:
            Tuple of (is_filtered, resource_type)
        """
        question_lower = question.lower()
        
        # Look for resource type requests
        resource_type = None
        if "librar" in question_lower and ("all" in question_lower or "show" in question_lower):
            resource_type = "libraries"
        elif "list" in question_lower and ("all" in question_lower or "show" in question_lower):
            resource_type = "lists"
        elif "page" in question_lower and ("all" in question_lower or "show" in question_lower):
            resource_type = "pages"
        
        return (resource_type is not None, resource_type)
    
    @staticmethod
    def extract_filter_keywords(question: str) -> List[str]:
        """Extract filter keywords from a question.
        
        Args:
            question: User question
            
        Returns:
            List of filter keywords
        """
        question_lower = question.lower()
        keywords = []
        
        # Common filter patterns
        filter_patterns = [
            "related to ", "about ", "for ", "regarding ", 
            "with ", "containing ", "that have "
        ]
        
        for pattern in filter_patterns:
            if pattern in question_lower:
                # Extract text after the pattern
                start_idx = question_lower.find(pattern) + len(pattern)
                remaining = question[start_idx:].strip()
                
                # Take the next few words as keywords
                words = remaining.split()[:3]  # Take up to 3 words
                keywords.extend([w.strip(".,?!") for w in words])
        
        # Also check for standalone topic words
        topic_indicators = ["hr", "human resources", "project", "finance", "it", 
                           "sales", "marketing", "kudos", "poll"]
        for topic in topic_indicators:
            if topic in question_lower:
                keywords.append(topic)
        
        return list(set(keywords))  # Remove duplicates


def format_resource_list(
    resources: List[Dict[str, Any]], 
    resource_type: str,
    include_description: bool = True
) -> str:
    """Format a list of resources for display.
    
    Args:
        resources: List of resources to format
        resource_type: Type of resource (for messaging)
        include_description: Whether to include descriptions
        
    Returns:
        Formatted string
    """
    if not resources:
        return f"No {resource_type} found."
    
    lines = []
    for resource in resources:
        name = resource.get("displayName", "") or resource.get("name", "")
        description = resource.get("description", "")
        
        if include_description and description:
            lines.append(f"• **{name}** - {description}")
        else:
            lines.append(f"• **{name}**")
    
    return "\n".join(lines)
