"""Web part composer for merging templates with generated content."""

import re
from typing import Dict, Any, List
from src.domain.value_objects import WebPart
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class WebPartComposer:
    """Composes final webparts by merging content templates with generated content.
    
    Replaces template placeholders with actual generated content to create
    ready-to-deploy webparts.
    """

    @staticmethod
    def _try_parse_list(value: Any) -> Any:
        """Attempt to parse a value as a list, handling stringified JSON."""
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                import json
                parsed = json.loads(value.replace("'", "\""))
                if isinstance(parsed, list):
                    return parsed
            except:
                pass
        return value

    @staticmethod
    def compose_webparts(
        template_webparts: List[WebPart],
        generated_content: Dict[str, Any],
    ) -> List[WebPart]:
        """Compose final webparts from template and generated content.
        
        Args:
            template_webparts: List of template webparts with placeholders
            generated_content: Dictionary with generated content values
            
        Returns:
            List of final webparts with all placeholders replaced
        """
        logger.debug(f"[WebPartComposer] Starting composition of {len(template_webparts)} webparts")
        logger.debug(f"[WebPartComposer] Generated content keys: {list(generated_content.keys())}")
        composed_webparts = []
        
        for i, template_wp in enumerate(template_webparts):
            try:
                logger.debug(f"[WebPartComposer] Composing webpart {i+1}/{len(template_webparts)}: {template_wp.type}")
                
                # Compose properties based on webpart type
                composed_props = WebPartComposer._compose_properties(
                    template_wp, 
                    generated_content
                )
                
                logger.debug(f"[WebPartComposer] Webpart {i+1} properties composed. Keys: {list(composed_props.keys())}")
                
                # Create new webpart with composed properties
                composed_wp = WebPart(
                    type=template_wp.type,
                    webpart_type=template_wp.webpart_type,
                    properties=composed_props,
                    id=template_wp.id,
                )
                composed_webparts.append(composed_wp)
                logger.debug(f"[WebPartComposer] Webpart {i+1} successfully composed")
                
            except Exception as e:
                logger.error(f"[WebPartComposer] Failed to compose webpart {i+1} ({template_wp.type}): {e}")
                # Add original template webpart as fallback
                composed_webparts.append(template_wp)
        
        logger.info(f"[WebPartComposer] Composition complete. Total webparts: {len(composed_webparts)}")
        return composed_webparts

    @staticmethod
    def _compose_properties(
        template_wp: WebPart,
        generated_content: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compose webpart properties by replacing placeholders.
        
        Args:
            template_wp: Template webpart
            generated_content: Dictionary with generated content
            
        Returns:
            Dictionary with composed properties
        """
        composed = {}
        
        for key, value in template_wp.properties.items():
            if isinstance(value, str):
                # SPECIAL CASE: if the value is EXACTLY a list placeholder, replace with list
                if value == "{QUICK_LINKS}":
                    composed[key] = WebPartComposer._try_parse_list(generated_content.get("quick_links", []))
                elif value == "{PERSONAS}":
                    composed[key] = WebPartComposer._try_parse_list(generated_content.get("personas", []))
                else:
                    # Normal string replacement
                    composed[key] = WebPartComposer._replace_placeholders(
                        value, 
                        generated_content
                    )
            elif isinstance(value, dict):
                # Recursively compose nested dicts
                composed[key] = WebPartComposer._compose_dict(
                    value, 
                    generated_content
                )
            elif isinstance(value, list):
                # Handle lists (e.g., quick_links)
                if key == "items" and "{QUICK_LINKS}" in str(value):
                    # Special handling for quick links placeholder within a list
                    composed[key] = WebPartComposer._try_parse_list(generated_content.get("quick_links", []))
                else:
                    # Recursively compose list items
                    composed[key] = [
                        WebPartComposer._compose_dict(item, generated_content)
                        if isinstance(item, dict)
                        else WebPartComposer._replace_placeholders(
                            str(item), 
                            generated_content
                        )
                        for item in value
                    ]
            else:
                # Keep non-string, non-dict values as-is
                composed[key] = value
        
        return composed

    @staticmethod
    def _compose_dict(
        template_dict: Dict[str, Any],
        generated_content: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Recursively compose dictionary by replacing placeholders.
        
        Args:
            template_dict: Template dictionary
            generated_content: Dictionary with generated content
            
        Returns:
            Dictionary with composed values
        """
        composed = {}
        
        for key, value in template_dict.items():
            if isinstance(value, str):
                if value == "{QUICK_LINKS}":
                    composed[key] = WebPartComposer._try_parse_list(generated_content.get("quick_links", []))
                elif value == "{PERSONAS}":
                    composed[key] = WebPartComposer._try_parse_list(generated_content.get("personas", []))
                else:
                    composed[key] = WebPartComposer._replace_placeholders(
                        value, 
                        generated_content
                    )
            elif isinstance(value, dict):
                composed[key] = WebPartComposer._compose_dict(
                    value, 
                    generated_content
                )
            elif isinstance(value, list):
                composed[key] = [
                    WebPartComposer._compose_dict(item, generated_content)
                    if isinstance(item, dict)
                    else WebPartComposer._replace_placeholders(
                        str(item), 
                        generated_content
                    )
                    for item in value
                ]
            else:
                composed[key] = value
        
        return composed

    @staticmethod
    def _replace_placeholders(
        text: str,
        generated_content: Dict[str, Any],
    ) -> str:
        """Replace template placeholders with generated content.
        
        Placeholders are in the format {PLACEHOLDER_NAME}.
        Maps placeholders to keys in generated_content dictionary.
        
        Args:
            text: Text with placeholders
            generated_content: Dictionary with replacement values
            
        Returns:
            Text with placeholders replaced
        """
        # Find all placeholders
        placeholder_pattern = r'\{([A-Z_]+)\}'
        
        def replacer(match):
            placeholder = match.group(1)
            
            # Map placeholders to keys in generated_content
            placeholder_map = {
                "PAGE_TITLE": "hero_title",
                "PAGE_DESCRIPTION": "hero_description",
                "HERO_IMAGE_URL": "hero_image_url",
                "PAGE_CONTENT": "page_content",
                "QUICK_LINKS": "quick_links",
            }
            
            key = placeholder_map.get(placeholder, placeholder.lower())
            value = generated_content.get(key, "")
            
            # Convert to string if needed (except for lists)
            if isinstance(value, list):
                # If it's a list being used in a string context, join titles if available
                # or return a clean string representation
                if all(isinstance(i, dict) and "title" in i for i in value):
                    return ", ".join(i["title"] for i in value)
                return str(value)
            return str(value) if value is not None else ""
        
        return re.sub(placeholder_pattern, replacer, text)

    @staticmethod
    def validate_webparts(webparts: List[WebPart]) -> List[str]:
        """Validate composed webparts.
        
        Args:
            webparts: List of webparts to validate
            
        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []
        
        if not webparts:
            errors.append("No webparts provided")
            return errors
        
        for i, wp in enumerate(webparts):
            # Check that type is not empty
            if not wp.type or not wp.type.strip():
                errors.append(f"Webpart {i} has empty type")
            
            # Check that properties is not empty
            if not wp.properties:
                errors.append(f"Webpart {i} ({wp.type}) has empty properties")
            
            # Check for remaining placeholders (indicates composition failure)
            # The previous check `if "{" in props_str and "}" in props_str:` was a false positive 
            # for any stringified dictionary. We use a precise regex to find exact unresolved placeholders.
            import re
            props_str = str(wp.properties)
            if re.search(r'\{[A-Z_]+\}', props_str):
                logger.warning(
                    f"Webpart {i} ({wp.type}) may contain unresolved placeholders"
                )
        
        return errors
