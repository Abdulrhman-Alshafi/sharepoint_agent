"""Field validation service for SharePoint list items."""

import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.domain.exceptions import SharePointProvisioningException


class FieldValidationError(SharePointProvisioningException):
    """Exception raised when field validation fails."""
    
    def __init__(self, field_name: str, message: str):
        self.field_name = field_name
        super().__init__(f"Validation error for field '{field_name}': {message}")


class FieldValidator:
    """Service for validating list item field values against list schema."""

    @staticmethod
    def validate_item_data(
        item_data: Dict[str, Any],
        list_schema: Dict[str, Any],
        is_update: bool = False
    ) -> List[str]:
        """Validate item data against list schema.
        
        Args:
            item_data: Dictionary of field values to validate
            list_schema: List schema with column definitions
            is_update: If True, required fields are not enforced
            
        Returns:
            List of validation warnings (non-fatal issues)
            
        Raises:
            FieldValidationError: If validation fails for any field
        """
        warnings = []
        columns = list_schema.get('columns', [])
        
        # Build column lookup by name
        column_lookup = {col['name']: col for col in columns}
        
        # Check required fields (only for create operations)
        if not is_update:
            for col in columns:
                if col.get('required') and col['name'] not in item_data:
                    # Skip system fields
                    if col['name'] not in ['Title', 'id', 'ID', 'Created', 'Modified', 'Author', 'Editor']:
                        raise FieldValidationError(
                            col['name'],
                            f"Required field '{col['name']}' is missing"
                        )
        
        # Validate each provided field
        for field_name, field_value in item_data.items():
            # Skip if field not in schema (might be system field)
            if field_name not in column_lookup:
                warnings.append(f"Field '{field_name}' not found in list schema - may be a system field")
                continue
            
            column = column_lookup[field_name]
            field_type = column.get('type', '').lower()
            
            # Validate based on type
            try:
                if field_type in ['text', 'string', 'note']:
                    FieldValidator._validate_text_field(field_name, field_value, column)
                elif field_type in ['number', 'integer', 'decimal']:
                    FieldValidator._validate_number_field(field_name, field_value, column)
                elif field_type in ['datetime', 'date']:
                    FieldValidator._validate_datetime_field(field_name, field_value, column)
                elif field_type in ['boolean', 'bool']:
                    FieldValidator._validate_boolean_field(field_name, field_value, column)
                elif field_type == 'choice':
                    FieldValidator._validate_choice_field(field_name, field_value, column, warnings)
                elif field_type in ['user', 'person']:
                    FieldValidator._validate_user_field(field_name, field_value, column)
                elif field_type == 'url':
                    FieldValidator._validate_url_field(field_name, field_value, column)
                elif field_type == 'lookup':
                    FieldValidator._validate_lookup_field(field_name, field_value, column)
                # Add more type validations as needed
            except FieldValidationError:
                raise
            except Exception as e:
                warnings.append(f"Could not fully validate field '{field_name}': {str(e)}")
        
        return warnings

    @staticmethod
    def _validate_text_field(field_name: str, value: Any, column: Dict[str, Any]):
        """Validate text field."""
        if not isinstance(value, str):
            raise FieldValidationError(field_name, f"Expected string, got {type(value).__name__}")
        
        max_length = column.get('maxLength')
        if max_length and len(value) > max_length:
            raise FieldValidationError(
                field_name,
                f"Text exceeds maximum length of {max_length} characters"
            )

    @staticmethod
    def _validate_number_field(field_name: str, value: Any, column: Dict[str, Any]):
        """Validate number field."""
        if not isinstance(value, (int, float)):
            # Try to convert
            try:
                float(value)
            except (ValueError, TypeError):
                raise FieldValidationError(field_name, f"Expected number, got {type(value).__name__}")
        
        min_value = column.get('min')
        max_value = column.get('max')
        
        numeric_value = float(value)
        if min_value is not None and numeric_value < min_value:
            raise FieldValidationError(field_name, f"Value {value} is below minimum {min_value}")
        if max_value is not None and numeric_value > max_value:
            raise FieldValidationError(field_name, f"Value {value} exceeds maximum {max_value}")

    @staticmethod
    def _validate_datetime_field(field_name: str, value: Any, column: Dict[str, Any]):
        """Validate datetime field."""
        if isinstance(value, datetime):
            return
        
        if isinstance(value, str):
            # Try to parse ISO 8601 format
            try:
                datetime.fromisoformat(value.replace('Z', '+00:00'))
                return
            except ValueError:
                raise FieldValidationError(
                    field_name,
                    f"Invalid date format. Expected ISO 8601 format (e.g., '2024-03-15T10:30:00Z')"
                )
        
        raise FieldValidationError(field_name, f"Expected datetime, got {type(value).__name__}")

    @staticmethod
    def _validate_boolean_field(field_name: str, value: Any, column: Dict[str, Any]):
        """Validate boolean field."""
        if not isinstance(value, bool):
            if isinstance(value, str) and value.lower() in ['true', 'false', 'yes', 'no']:
                return
            raise FieldValidationError(field_name, f"Expected boolean, got {type(value).__name__}")

    @staticmethod
    def _validate_choice_field(field_name: str, value: Any, column: Dict[str, Any], warnings: List[str]):
        """Validate choice field."""
        if not isinstance(value, str):
            raise FieldValidationError(field_name, f"Expected string choice, got {type(value).__name__}")
        
        choices = column.get('choices', [])
        if choices and value not in choices:
            # This is a warning, not an error, as choices might be updated
            warnings.append(
                f"Field '{field_name}': Value '{value}' is not in predefined choices: {choices}"
            )

    @staticmethod
    def _validate_user_field(field_name: str, value: Any, column: Dict[str, Any]):
        """Validate user/person field."""
        if isinstance(value, dict):
            # Expecting {email: ..., displayName: ...} or similar
            if 'email' not in value and 'id' not in value:
                raise FieldValidationError(
                    field_name,
                    "User field must contain 'email' or 'id'"
                )
        elif isinstance(value, str):
            # Validate email format if it looks like an email
            if '@' in value:
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, value):
                    raise FieldValidationError(field_name, f"Invalid email format: {value}")
        else:
            raise FieldValidationError(
                field_name,
                f"User field must be a dict or string, got {type(value).__name__}"
            )

    @staticmethod
    def _validate_url_field(field_name: str, value: Any, column: Dict[str, Any]):
        """Validate URL field."""
        if isinstance(value, dict):
            if 'Url' not in value and 'url' not in value:
                raise FieldValidationError(field_name, "URL field must contain 'Url' or 'url' property")
        elif isinstance(value, str):
            # Basic URL validation
            url_pattern = r'^https?://.+\..+'
            if not re.match(url_pattern, value, re.IGNORECASE):
                raise FieldValidationError(field_name, f"Invalid URL format: {value}")
        else:
            raise FieldValidationError(
                field_name,
                f"URL field must be a dict or string, got {type(value).__name__}"
            )

    @staticmethod
    def _validate_lookup_field(field_name: str, value: Any, column: Dict[str, Any]):
        """Validate lookup field."""
        if not isinstance(value, (int, str, dict)):
            raise FieldValidationError(
                field_name,
                f"Lookup field must be an ID (int/str) or dict, got {type(value).__name__}"
            )
        
        if isinstance(value, dict) and 'LookupId' not in value and 'id' not in value:
            raise FieldValidationError(
                field_name,
                "Lookup field dict must contain 'LookupId' or 'id'"
            )

    @staticmethod
    def get_field_type_hint(field_type: str) -> str:
        """Get a user-friendly hint for the expected field type.
        
        Args:
            field_type: SharePoint field type
            
        Returns:
            Human-readable description and example
        """
        hints = {
            'text': "Text string (e.g., 'John Doe')",
            'note': "Long text (e.g., 'This is a detailed description...')",
            'number': "Number (e.g., 42 or 3.14)",
            'datetime': "Date/time in ISO format (e.g., '2024-03-15T10:30:00Z')",
            'boolean': "True or False",
            'choice': "One of the predefined choices",
            'user': "Email address (e.g., 'user@example.com')",
            'url': "Web address (e.g., 'https://example.com')",
            'lookup': "ID of related item (e.g., 5)",
        }
        return hints.get(field_type.lower(), f"Value of type {field_type}")
