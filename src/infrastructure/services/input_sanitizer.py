"""Input sanitization utilities for chat messages and user inputs."""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum message length
MAX_MESSAGE_LENGTH = 2000

# Patterns that may indicate prompt injection attempts
SUSPICIOUS_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|prompts|rules)",
    r"system\s*:\s*you\s+are",
    r"new\s+instructions",
    r"forget\s+(everything|all|previous)",
    r"<\s*script",
    r"javascript\s*:",
    r"<\s*iframe",
]


class InputSanitizer:
    """Sanitize and validate user inputs."""
    
    @staticmethod
    def sanitize_message(message: str) -> str:
        """Sanitize a chat message.
        
        Args:
            message: Raw user message
            
        Returns:
            Sanitized message
            
        Raises:
            ValueError: If message is invalid or potentially malicious
        """
        if not message:
            raise ValueError("Message cannot be empty")
        
        # Remove leading/trailing whitespace
        message = message.strip()
        
        # Check length
        if len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message too long (max {MAX_MESSAGE_LENGTH} characters)")
        
        # Remove excessive whitespace and control characters
        message = re.sub(r'\s+', ' ', message)
        message = ''.join(char for char in message if char.isprintable() or char in ['\n', '\t', ' '])
        
        # Check for prompt injection patterns
        message_lower = message.lower()
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                raise ValueError("Potential prompt injection detected")
        
        return message
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize a filename.
        
        Args:
            filename: Raw filename
            
        Returns:
            Sanitized filename
        """
        if not filename:
            raise ValueError("Filename cannot be empty")
        
        # Remove path traversal attempts
        from pathlib import Path
        filename = Path(filename).name

        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:250] + ('.' + ext if ext else '')
        
        return filename
    
    @staticmethod
    def sanitize_list_name(name: str) -> str:
        """Sanitize a SharePoint list name.
        
        Args:
            name: Raw list name
            
        Returns:
            Sanitized list name
        """
        if not name:
            raise ValueError("List name cannot be empty")
        
        # SharePoint list names have specific restrictions
        # Remove invalid characters
        name = re.sub(r'[<>:"/\\|?*#%&{}]', '', name)
        
        # Trim to reasonable length (SharePoint limit is 255)
        if len(name) > 255:
            name = name[:255]
        
        return name.strip()
