"""Utility for editing SharePoint page canvas JSON content."""

from typing import Dict, Any, List, Optional
import json
import copy
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class CanvasEditor:
    """Helper class for parsing and manipulating SharePoint page canvas content."""
    
    @staticmethod
    def parse_canvas(canvas_json: str) -> List[Dict[str, Any]]:
        """Parse canvas JSON string into structured list.
        
        Args:
            canvas_json: Canvas content JSON string
            
        Returns:
            List of canvas control objects
        """
        if not canvas_json:
            return []
        
        try:
            if isinstance(canvas_json, str):
                return json.loads(canvas_json)
            elif isinstance(canvas_json, list):
                return canvas_json
            else:
                return []
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse canvas JSON: %s", e)
            return []
    
    @staticmethod
    def serialize_canvas(canvas_controls: List[Dict[str, Any]]) -> str:
        """Serialize canvas controls back to JSON string.
        
        Args:
            canvas_controls: List of canvas control objects
            
        Returns:
            JSON string
        """
        return json.dumps(canvas_controls, separators=(',', ':'))
    
    @staticmethod
    def add_web_part(canvas_controls: List[Dict[str, Any]], web_part: Dict[str, Any], 
                      position: str = "end", section_index: int = 0, column_index: int = 0) -> List[Dict[str, Any]]:
        """Add a web part to canvas at specified position.
        
        Args:
            canvas_controls: Existing canvas controls
            web_part: Web part control to add
            position: "start", "end", or "index" (default: "end")
            section_index: Section index for positioned insert
            column_index: Column index within section
            
        Returns:
            Updated canvas controls list
        """
        canvas = copy.deepcopy(canvas_controls)
        
        if position == "start":
            canvas.insert(0, web_part)
        elif position == "end":
            canvas.append(web_part)
        elif position == "index" and section_index < len(canvas):
            # Insert at specific section
            canvas.insert(section_index, web_part)
        else:
            canvas.append(web_part)
        
        return canvas
    
    @staticmethod
    def remove_web_part(canvas_controls: List[Dict[str, Any]], web_part_id: str) -> List[Dict[str, Any]]:
        """Remove a web part from canvas by ID.
        
        Args:
            canvas_controls: Existing canvas controls
            web_part_id: ID of web part to remove
            
        Returns:
            Updated canvas controls list
        """
        canvas = copy.deepcopy(canvas_controls)
        canvas = [control for control in canvas if control.get("id") != web_part_id]
        return canvas
    
    @staticmethod
    def remove_web_part_by_index(canvas_controls: List[Dict[str, Any]], index: int) -> List[Dict[str, Any]]:
        """Remove a web part from canvas by index.
        
        Args:
            canvas_controls: Existing canvas controls
            index: Index of web part to remove
            
        Returns:
            Updated canvas controls list
        """
        canvas = copy.deepcopy(canvas_controls)
        if 0 <= index < len(canvas):
            canvas.pop(index)
        return canvas
    
    @staticmethod
    def reorder_sections(canvas_controls: List[Dict[str, Any]], new_order: List[int]) -> List[Dict[str, Any]]:
        """Reorder canvas sections/controls.
        
        Args:
            canvas_controls: Existing canvas controls
            new_order: List of indices in desired order
            
        Returns:
            Reordered canvas controls list
        """
        canvas = copy.deepcopy(canvas_controls)
        
        if len(new_order) != len(canvas):
            logger.warning("new_order length doesn't match canvas controls length")
            return canvas
        
        reordered = [canvas[i] for i in new_order if 0 <= i < len(canvas)]
        return reordered
    
    @staticmethod
    def find_web_part_by_type(canvas_controls: List[Dict[str, Any]], web_part_type: str) -> List[Dict[str, Any]]:
        """Find all web parts of a specific type.
        
        Args:
            canvas_controls: Canvas controls to search
            web_part_type: Web part type to find (e.g., "TextWebPart")
            
        Returns:
            List of matching web parts
        """
        matches = []
        for control in canvas_controls:
            if control.get("webPartType") == web_part_type:
                matches.append(control)
        return matches
    
    @staticmethod
    def update_web_part_properties(canvas_controls: List[Dict[str, Any]], web_part_id: str, 
                                     new_properties: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Update properties of a specific web part.
        
        Args:
            canvas_controls: Existing canvas controls
            web_part_id: ID of web part to update
            new_properties: New properties to merge
            
        Returns:
            Updated canvas controls list
        """
        canvas = copy.deepcopy(canvas_controls)
        
        for control in canvas:
            if control.get("id") == web_part_id:
                web_part_data = control.get("webPartData", {})
                if isinstance(web_part_data, dict):
                    web_part_data.update(new_properties)
                    control["webPartData"] = web_part_data
                break
        
        return canvas
    
    @staticmethod
    def extract_text_content(canvas_controls: List[Dict[str, Any]]) -> str:
        """Extract all text content from canvas for analysis.
        
        Args:
            canvas_controls: Canvas controls to extract from
            
        Returns:
            Combined text content
        """
        text_parts = []
        
        for control in canvas_controls:
            web_part_type = control.get("webPartType")
            
            if web_part_type == "TextWebPart":
                data = control.get("webPartData", {})
                if isinstance(data, dict):
                    text = data.get("innerHTML", "") or data.get("text", "")
                    if text:
                        text_parts.append(text)
            
            # Extract from other web part types if they contain text
            if "title" in control:
                text_parts.append(control["title"])
        
        return " ".join(text_parts)
    
    @staticmethod
    def get_web_part_summary(canvas_controls: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Get a summary of all web parts in canvas.
        
        Args:
            canvas_controls: Canvas controls to summarize
            
        Returns:
            List of web part summaries with type, title, and id
        """
        summaries = []
        
        for i, control in enumerate(canvas_controls):
            summary = {
                "index": str(i),
                "type": control.get("webPartType", "Unknown"),
                "title": control.get("title", "Untitled"),
                "id": control.get("id", "")
            }
            summaries.append(summary)
        
        return summaries
    
    @staticmethod
    def create_text_web_part(text_content: str, title: str = "") -> Dict[str, Any]:
        """Create a simple text web part control.
        
        Args:
            text_content: HTML text content
            title: Optional title
            
        Returns:
            Text web part control object
        """
        import uuid
        
        return {
            "id": str(uuid.uuid4()),
            "webPartType": "TextWebPart",
            "title": title,
            "webPartData": {
                "innerHTML": text_content
            }
        }
    
    @staticmethod
    def create_quick_links_web_part(links: List[Dict[str, str]], title: str = "Quick Links") -> Dict[str, Any]:
        """Create a Quick Links web part control.
        
        Args:
            links: List of links with 'url' and 'title' keys
            title: Web part title
            
        Returns:
            Quick Links web part control object
        """
        import uuid
        
        return {
            "id": str(uuid.uuid4()),
            "webPartType": "QuickLinksWebPart",
            "title": title,
            "webPartData": {
                "links": links,
                "layoutId": "List"  # Options: List, Compact, Filmstrip, Button
            }
        }
    
    @staticmethod
    def create_list_web_part(list_id: str, title: str = "") -> Dict[str, Any]:
        """Create a List web part control.
        
        Args:
            list_id: SharePoint list ID
            title: Optional title
            
        Returns:
            List web part control object
        """
        import uuid
        
        return {
            "id": str(uuid.uuid4()),
            "webPartType": "ListWebPart",
            "title": title,
            "webPartData": {
                "listId": list_id
            }
        }
