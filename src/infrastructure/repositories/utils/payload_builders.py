"""Payload builder utilities for SharePoint API requests.

All knowledge of the Microsoft Graph / REST API wire format lives here.
Domain entities intentionally carry no to_graph_api_payload / from_graph_api_response
callables — those have been removed and replaced with the static helpers in this module.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class PayloadBuilders:
    """Build request payloads for various SharePoint APIs."""

    @staticmethod
    def build_list_payload(sp_list: Any) -> Dict[str, Any]:
        """Build Graph API payload for creating/updating a list."""
        columns_payload: List[Dict[str, Any]] = []
        for col in sp_list.columns:
            if col.name.lower() == "title":
                continue
            col_payload: Dict[str, Any] = {
                "name": col.name,
                "required": col.required,
            }
            type_mapping = {
                "text": {"text": {}},
                "note": {"text": {"allowMultipleLines": True}},
                "number": {"number": {}},
                "dateTime": {"dateTime": {}},
                "choice": {"choice": {"choices": getattr(col, "choices", [])} if getattr(col, "choices", []) else {}},
                "boolean": {"boolean": {}},
                "lookup": {"lookup": {}},
                "managed_metadata": {"term": {}},
                "currency": {"currency": {}},
                "personOrGroup": {"personOrGroup": {}},
                "hyperlinkOrPicture": {"hyperlinkOrPicture": {}},
                "geolocation": {"geolocation": {}},
            }
            col_payload.update(type_mapping.get(col.type, {"text": {}}))
            columns_payload.append(col_payload)

        return {
            "displayName": sp_list.title,
            "description": sp_list.description,
            "list": {"template": sp_list.template or "genericList"},
            "columns": columns_payload,
        }

    @staticmethod
    def build_page_payload(sp_page: Any) -> Dict[str, Any]:
        """Build Graph API sitePage payload for creating/updating a page."""
        web_parts_payload = []
        for wp in sp_page.webparts:
            if wp.type.lower() in ["text", "rte"]:
                wp_data: Dict[str, Any] = {
                    "type": "rte",
                    "innerHtml": wp.properties.get("content", wp.properties.get("text", "")),
                }
            else:
                wp_data = {
                    "type": "custom",
                    "customWebPart": {"type": wp.type, "properties": wp.properties},
                }
            if wp.id:
                wp_data["id"] = wp.id
            web_parts_payload.append(wp_data)

        return {
            "title": sp_page.title,
            "pageLayout": "article",
            "canvasLayout": {
                "horizontalSections": [
                    {
                        "layout": "oneColumn",
                        "columns": [
                            {"id": "1", "width": 12, "webparts": web_parts_payload}
                        ],
                    }
                ]
            },
        }

    @staticmethod
    def build_library_payload(library: Any) -> Dict[str, Any]:
        """Build Graph API payload for creating a document library."""
        return {
            "displayName": library.title,
            "description": library.description,
            "list": {"template": "documentLibrary"},
        }

    @staticmethod
    def library_item_from_graph_response(
        data: Dict[str, Any],
        library_id: str,
        drive_id: str,
    ) -> Any:  # returns LibraryItem
        """Construct a ``LibraryItem`` domain entity from a raw Graph API drive-item response.

        This factory lives in the infrastructure layer so that the domain entity
        ``LibraryItem`` carries no knowledge of the Graph API wire format.
        """
        # Import here to avoid circular dependency — this module is already infra.
        from src.domain.entities.document import LibraryItem  # noqa: PLC0415

        file_info = data.get("file", {})
        created_by_info = data.get("createdBy", {}).get("user", {})
        modified_by_info = data.get("lastModifiedBy", {}).get("user", {})

        return LibraryItem(
            name=data.get("name", ""),
            item_id=data.get("id", ""),
            library_id=library_id,
            drive_id=drive_id,
            size=data.get("size", 0),
            created_datetime=(
                datetime.fromisoformat(data["createdDateTime"].replace("Z", "+00:00"))
                if "createdDateTime" in data
                else None
            ),
            modified_datetime=(
                datetime.fromisoformat(data["lastModifiedDateTime"].replace("Z", "+00:00"))
                if "lastModifiedDateTime" in data
                else None
            ),
            created_by=created_by_info.get("displayName"),
            modified_by=modified_by_info.get("displayName"),
            web_url=data.get("webUrl"),
            download_url=data.get("@microsoft.graph.downloadUrl"),
            file_type=(
                ("." + data.get("name", "").rsplit(".", 1)[-1].lower())
                if "." in data.get("name", "")
                else None
            ),
            mime_type=file_info.get("mimeType"),
            custom_metadata={},
        )

    @staticmethod
    def build_column_payload(column: Any) -> Dict[str, Any]:
        """Build Graph API payload for creating a column.
        
        Args:
            column: SPColumn value object
            
        Returns:
            Dictionary payload for Graph API
        """
        col_payload = {
            "name": column.name,
            "required": column.required
        }
        
        type_mapping = {
            "text": {"text": {}},
            "note": {"text": {"allowMultipleLines": True}},
            "number": {"number": {}},
            "dateTime": {"dateTime": {}},
            "choice": {
                "choice": {
                    "choices": getattr(column, "choices", [])
                } if getattr(column, "choices", []) else {}
            },
            "boolean": {"boolean": {}},
            "lookup": {"lookup": {}},
            "managed_metadata": {"term": {}},
            "currency": {"currency": {}},
            "personOrGroup": {"personOrGroup": {}},
            "hyperlinkOrPicture": {"hyperlinkOrPicture": {}},
            "geolocation": {"geolocation": {}}
        }
        
        col_payload.update(type_mapping.get(column.type, {"text": {}}))
        return col_payload

    @staticmethod
    def build_group_payload(group: Any) -> Dict[str, Any]:
        """Build REST API payload for creating a SharePoint group.
        
        Args:
            group: SharePointGroup entity
            
        Returns:
            Dictionary payload for REST API
        """
        return {
            "__metadata": {"type": "SP.Group"},
            "Title": group.name,
            "Description": group.description or f"{group.name} SharePoint Group",
        }

    @staticmethod
    def build_content_type_payload(content_type: Any) -> Dict[str, Any]:
        """Build Graph API payload for creating a content type.

        Args:
            content_type: ContentType entity

        Returns:
            Dictionary payload for Graph API
        """
        return {
            "name": content_type.name,
            "description": content_type.description,
            "base": {"name": content_type.parent_type},
        }

    @staticmethod
    def build_term_set_payload(term_set: Any) -> Dict[str, Any]:
        """Build Graph API payload for creating a term set.

        Args:
            term_set: TermSet entity

        Returns:
            Dictionary payload for Graph termStore API
        """
        return {
            "localizedNames": [
                {"name": term_set.name, "languageTag": "en-US"}
            ],
            "description": "Created by SharePoint AI Agent",
        }

    @staticmethod
    def build_term_payload(term_label: str) -> Dict[str, Any]:
        """Build Graph API payload for a single term inside a term set.

        Args:
            term_label: Display label for the term

        Returns:
            Dictionary payload for term creation
        """
        return {
            "labels": [{"name": term_label, "languageTag": "en-US", "isDefault": True}]
        }

    @staticmethod
    def build_view_payload(view: Any) -> Dict[str, Any]:
        """Build REST API payload for creating a list view.

        Args:
            view: SPView entity

        Returns:
            Dictionary payload for REST API
        """
        return {
            "__metadata": {"type": "SP.View"},
            "Title": view.title,
            "RowLimit": view.row_limit,
            "ViewQuery": view.query,
        }

    @staticmethod
    def build_site_payload(sp_site: Any) -> Dict[str, Any]:
        """Build Graph API payload for creating a SharePoint site.

        Args:
            sp_site: SPSite entity

        Returns:
            Dictionary payload for Graph API
        """
        return {
            "displayName": sp_site.title,
            "description": getattr(sp_site, "description", ""),
            "sharepointIds": {"siteUrl": getattr(sp_site, "url", "")},
        }
