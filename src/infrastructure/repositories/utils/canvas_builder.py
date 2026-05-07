"""Canvas content builder for SharePoint pages.

Supports rich webpart types:
  Text / RTE     — inline HTML text
  Hero           — banner with title overlay
  Image          — inline image with caption
  QuickLinks     — grid of icon+link cards
  News           — news feed webpart
  People         — team member cards
  List           — embedded SharePoint list view
  DocumentLibrary — embedded library view
  Events         — calendar/event webpart

Microsoft Graph API canvas layout reference:
  https://learn.microsoft.com/en-us/graph/api/sitepage-create
"""

import json
import uuid
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Official Microsoft webpart GUIDs (stable, public)
# ---------------------------------------------------------------------------
_WP_GUID_HERO           = "c4bd7b2f-7b6e-4599-8485-16504575f590"
_WP_GUID_IMAGE          = "d1d91016-032f-456d-98a4-721247c305e8"
_WP_GUID_QUICK_LINKS    = "c70391ea-0b10-4ee9-b2b4-006d3fcad0cd"
_WP_GUID_NEWS           = "8c88f208-6c77-4bdb-86a0-0c47b4316588"
_WP_GUID_PEOPLE         = "7f718435-ee4d-431c-bdbf-9c4ff326f46e"
_WP_GUID_LIST           = "f92bf067-bc19-489e-a556-7fe9f3765b7b"
_WP_GUID_DOC_LIBRARY    = "b7dd04e1-19ce-4b24-9132-b60a1c2b910d"
_WP_GUID_EVENTS         = "20745d7d-8581-4a6c-bf26-68279bc914f0"


def _new_id() -> str:
    return str(uuid.uuid4())


def _position(zone: int, section: int, control: int) -> dict:
    return {
        "zoneIndex": zone,
        "sectionIndex": section,
        "controlIndex": control,
        "layoutIndex": 1,
    }


def _ensure_list(items: Any) -> list:
    """Ensure items is a list, handling stringified JSON and non-list inputs."""
    if isinstance(items, list):
        return items
    if isinstance(items, str):
        if items.strip().startswith("["):
            try:
                import json
                parsed = json.loads(items.replace("'", "\""))
                if isinstance(parsed, list):
                    return parsed
            except:
                pass
        return [{"title": items, "displayName": items, "name": items, "url": "", "iconType": 0}]
    return []


def _text_item(wp: Any, zone: int, section: int, control: int) -> dict:
    """controlType 4 — inline HTML text."""
    return {
        "controlType": 4,
        "id": wp.id or _new_id(),
        "position": _position(zone, section, control),
        "innerHTML": wp.properties.get("content", wp.properties.get("text", "")),
        "emphasis": {},
    }


def _webpart_item(wp_type_id: str, title: str, props: dict,
                  wp: Any, zone: int, section: int, control: int) -> dict:
    """controlType 3 — client-side web part with data blob."""
    return {
        "controlType": 3,
        "id": wp.id or _new_id(),
        "position": _position(zone, section, control),
        "webPartType": wp_type_id,
        "webPartData": {
            "id": wp_type_id,
            "instanceId": wp.id or _new_id(),
            "title": title,
            "audiences": [],
            "serverProcessedContent": {"htmlStrings": {}, "searchablePlainTexts": {}, "imageSources": {}, "links": {}},
            "dataVersion": "1.0",
            "properties": props,
        },
    }


def _build_hero(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    hero_items = _ensure_list(props.get("items", []))
    if not hero_items:
        hero_items = [{
            "title": props.get("title", "Welcome"),
            "description": props.get("description", ""),
            "imageSourceType": 4,
            "imageSource": props.get("imageSource", ""),
            "titleLink": props.get("link", ""),
            "layout": "Basic",
        }]
    return _webpart_item(
        _WP_GUID_HERO, "Hero", {"heroLayoutTheme": 0, "isSupportedByTargeting": False, "items": hero_items},
        wp, zone, section, control
    )


def _build_image(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    return _webpart_item(
        _WP_GUID_IMAGE, "Image",
        {
            "imageSourceType": 2,
            "imageSource": props.get("imageSource", ""),
            "altText": props.get("altText", props.get("caption", "")),
            "caption": props.get("caption", ""),
            "siteId": "",
            "webId": "",
            "listId": "",
            "uniqueId": "",
        },
        wp, zone, section, control
    )


def _build_quick_links(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    raw_items = _ensure_list(props.get("items", []))
    
    items = []
    for item in raw_items:
        if isinstance(item, str):
            items.append({"title": item, "url": "", "iconType": 0})
        elif isinstance(item, dict):
            items.append({
                "title": item.get("title", item.get("name", "")),
                "url": item.get("url", item.get("link", "")),
                "iconType": item.get("iconType", 0),
            })
    return _webpart_item(
        _WP_GUID_QUICK_LINKS, "Quick links",
        {
            "items": items,
            "layoutId": "Button",
            "shouldShowThumbnail": True,
            "hideWebPartWhenEmpty": True,
            "dataProviderId": "QuickLinks",
        },
        wp, zone, section, control
    )


def _build_news(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    return _webpart_item(
        _WP_GUID_NEWS, "News",
        {
            "layoutId": "GridLayout",
            "dataProviderId": "news",
            "emptyStateHelpItemsCount": 1,
            "newsDataSourceProp": props.get("newsSource", 2),
            "newsSiteList": props.get("newsSiteList", []),
            "renderItemsCount": props.get("count", 5),
        },
        wp, zone, section, control
    )


def _build_people(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    personas = _ensure_list(props.get("personas", props.get("persons", [])))
    people_items = []
    for p in personas:
        if isinstance(p, str):
            people_items.append({"id": p, "upn": p, "displayName": p})
        else:
            people_items.append({
                "id": p.get("id", p.get("email", "")),
                "upn": p.get("upn", p.get("email", "")),
                "displayName": p.get("displayName", p.get("name", "")),
            })
    return _webpart_item(
        _WP_GUID_PEOPLE, "People",
        {
            "persons": people_items,
            "layout": 1,
            "personaSize": props.get("personaSize", 14),
        },
        wp, zone, section, control
    )


def _build_list(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    return _webpart_item(
        _WP_GUID_LIST, "List",
        {
            "isDocumentLibrary": False,
            "showDefaultDocumentLibrary": False,
            "webpartHeightKey": 4,
            "listId": props.get("listId", ""),
            "webId": props.get("webId", ""),
            "siteId": props.get("siteId", ""),
            "title": props.get("title", ""),
            "selectedView": props.get("viewId", ""),
            "hideCommandBar": False,
        },
        wp, zone, section, control
    )


def _build_document_library(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    return _webpart_item(
        _WP_GUID_DOC_LIBRARY, "Document library",
        {
            "isDocumentLibrary": True,
            "showDefaultDocumentLibrary": True,
            "webpartHeightKey": 4,
            "listId": props.get("listId", ""),
            "webId": props.get("webId", ""),
            "siteId": props.get("siteId", ""),
            "title": props.get("title", ""),
            "selectedView": props.get("viewId", ""),
            "hideCommandBar": False,
        },
        wp, zone, section, control
    )


def _build_events(wp: Any, zone: int, section: int, control: int) -> dict:
    props = wp.properties
    return _webpart_item(
        _WP_GUID_EVENTS, "Events",
        {
            "layoutId": "filmStrip",
            "dataProviderId": "Events",
            "listId": props.get("listId", ""),
            "webId": props.get("webId", ""),
            "dateRangeType": props.get("dateRangeType", 1),
            "maxItemsPerPage": props.get("count", 3),
        },
        wp, zone, section, control
    )


class CanvasContentBuilder:
    """Build SharePoint canvas content JSON from webparts."""

    @staticmethod
    def build_graph_webparts(webparts: List[Any]) -> List[Dict[str, Any]]:
        """Build SharePoint webparts in Microsoft Graph API v1.0 format.
        
        Args:
            webparts: List of WebPart value objects
            
        Returns:
            List of webpart dictionaries for Graph API v1.0
        """
        graph_webparts = []
        
        for wp in webparts:
            _wpt = getattr(wp, "webpart_type", "Text") or "Text"
            wtype = (_wpt if _wpt.lower() != "text" else wp.type or "text").lower()
            
            if wtype in ("text", "rte"):
                graph_webparts.append({
                    "type": "rte",
                    "innerHtml": wp.properties.get("content", wp.properties.get("text", ""))
                })
            else:
                # Map domain webpart types to known GUIDs if possible
                type_map = {
                    "hero": _WP_GUID_HERO,
                    "image": _WP_GUID_IMAGE,
                    "quicklinks": _WP_GUID_QUICK_LINKS,
                    "quick_links": _WP_GUID_QUICK_LINKS,
                    "quick links": _WP_GUID_QUICK_LINKS,
                    "news": _WP_GUID_NEWS,
                    "people": _WP_GUID_PEOPLE,
                    "list": _WP_GUID_LIST,
                    "documentlibrary": _WP_GUID_DOC_LIBRARY,
                    "document_library": _WP_GUID_DOC_LIBRARY,
                    "document library": _WP_GUID_DOC_LIBRARY,
                    "events": _WP_GUID_EVENTS,
                }
                template_id = type_map.get(wtype, wp.webpart_type)
                
                # Special handling for rich webpart properties transformation
                # For Graph v1.0, we can often send the properties directly if they match
                # what the webpart expects.
                props = wp.properties
                
                # Some webparts need structural transformation even for Graph v1.0
                if wtype in ("quicklinks", "quick_links", "quick links"):
                    # Use the same logic as _build_quick_links to ensure items is a list
                    raw_items = _ensure_list(props.get("items", []))
                    
                    processed_items = []
                    for item in raw_items:
                        if isinstance(item, str):
                            processed_items.append({"title": item, "url": "", "iconType": 0})
                        elif isinstance(item, dict):
                            processed_items.append({
                                "title": item.get("title", item.get("name", "")),
                                "url": item.get("url", item.get("link", "")),
                                "iconType": item.get("iconType", 0),
                            })
                    props = {**props, "items": processed_items}
                
                graph_webparts.append({
                    "type": "custom",
                    "customWebPart": {
                        "templateId": template_id,
                        "properties": props
                    }
                })
        
        return graph_webparts

    @staticmethod
    def build(webparts: List[Any]) -> str:
        """Build SharePoint canvas content from a list of WebPart value objects.

        Each WebPart's ``webpart_type`` field (case-insensitive) determines
        which Graph API JSON structure is emitted.  Falls back to a plain
        text item for unknown types.

        Args:
            webparts: List of :class:`~src.domain.value_objects.WebPart` instances.

        Returns:
            JSON string suitable for the ``canvasLayout`` Graph API field.
        """
        canvas: list = []

        for idx, wp in enumerate(webparts):
            zone, section, control = 1, 1, idx + 1
            # Use explicit webpart_type only when it's overridden from the default.
            # Otherwise fall back to wp.type so e.g. type="NewsWebPart" is not
            # treated as a plain text webpart just because webpart_type defaulted to "Text".
            _wpt = getattr(wp, "webpart_type", "Text") or "Text"
            wtype = (_wpt if _wpt.lower() != "text" else wp.type or "text").lower()

            if wtype in ("text", "rte"):
                item = _text_item(wp, zone, section, control)
            elif wtype == "hero":
                item = _build_hero(wp, zone, section, control)
            elif wtype == "image":
                item = _build_image(wp, zone, section, control)
            elif wtype in ("quicklinks", "quick_links", "quick links"):
                item = _build_quick_links(wp, zone, section, control)
            elif wtype == "news":
                item = _build_news(wp, zone, section, control)
            elif wtype == "people":
                item = _build_people(wp, zone, section, control)
            elif wtype == "list":
                item = _build_list(wp, zone, section, control)
            elif wtype in ("documentlibrary", "document_library", "document library"):
                item = _build_document_library(wp, zone, section, control)
            elif wtype == "events":
                item = _build_events(wp, zone, section, control)
            else:
                # Unknown/custom webpart type — emit a controlType 3 web part
                item = _webpart_item(
                    wp_type_id=_new_id(),
                    title=wp.type,
                    props=wp.properties,
                    wp=wp,
                    zone=zone,
                    section=section,
                    control=control,
                )

            canvas.append(item)

        return json.dumps(canvas) if canvas else "[]"

