"""Content analyzer service for understanding SharePoint resources."""

from typing import Optional, List, Dict, Any
import asyncio
import functools
import json
from datetime import datetime

from src.domain.entities.conversation import ContentAnalysis
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.logging import get_logger
from pydantic import BaseModel, Field

logger = get_logger(__name__)


class ContentSummary(BaseModel):
    """Pydantic model for AI-generated content summary."""
    summary: str = Field(description="2-3 sentence summary of the content")
    detailed_description: str = Field(description="Comprehensive explanation of what this resource is for")
    main_topics: List[str] = Field(description="List of main topics or keywords (3-8 items)")
    purpose: str = Field(description="Inferred purpose or goal of this resource")
    audience: str = Field(description="Inferred target audience or users")
    confidence: float = Field(description="Confidence score 0.0-1.0", ge=0.0, le=1.0)
    suggested_actions: List[str] = Field(
        default_factory=list,
        description=(
            "3-4 smart, specific follow-up actions the user can take, written as natural commands. "
            "Base these on the actual data: e.g. if the list has a Status column with 'Done'/'In Progress' values, "
            "suggest 'Show me all Done tasks' or 'How many tasks are In Progress?'. "
            "If it tracks employees, suggest 'Who was the employee of the month in March?'. "
            "Make every action specific to the real content, never generic."
        )
    )


class ContentAnalyzerService:
    """Service for analyzing SharePoint content to understand its purpose and structure."""
    
    def __init__(self, graph_client, rest_client, list_service, page_service, library_service):
        """Initialize content analyzer.
        
        Args:
            graph_client: Graph API client
            rest_client: REST API client
            list_service: List service for retrieving list data
            page_service: Page service for retrieving page data
            library_service: Library service for retrieving library data
        """
        self.graph_client = graph_client
        self.rest_client = rest_client
        self.list_service = list_service
        self.page_service = page_service
        self.library_service = library_service
        self._cache: Dict[str, ContentAnalysis] = {}  # Simple cache
        self._cache_ttl = 3600  # 1 hour
    
    async def analyze_site(self, site_id: str) -> ContentAnalysis:
        """Analyze a SharePoint site to understand its content and purpose.
        
        Args:
            site_id: SharePoint site ID
            
        Returns:
            ContentAnalysis with site understanding
        """
        cache_key = f"site_{site_id}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if (datetime.now().timestamp() - cached.analyzed_at) < self._cache_ttl:
                return cached
        
        # Gather site information
        site_info = await self._get_site_info(site_id)
        lists = await self.list_service.get_all_lists(site_id)
        libraries = await self.library_service.get_all_libraries(site_id)
        
        # Extract component information
        components = []
        for lst in lists:
            components.append({
                "type": "list",
                "name": lst.get("displayName", "Unknown"),
                "id": lst.get("id", ""),
                "description": lst.get("description", "")
            })
        
        for lib in libraries:
            components.append({
                "type": "library",
                "name": lib.get("name", "Unknown"),
                "id": lib.get("id", ""),
                "description": lib.get("description", "")
            })
        
        # Build context for AI analysis
        context = self._build_site_context(site_info, lists, libraries)
        
        # Get AI summary
        summary_data = await self._generate_ai_summary(
            resource_type="site",
            resource_name=site_info.get("displayName", "Unknown Site"),
            context=context
        )
        
        # Build ContentAnalysis
        analysis = ContentAnalysis(
            resource_type="site",
            resource_id=site_id,
            resource_name=site_info.get("displayName", "Unknown Site"),
            summary=summary_data.summary,
            detailed_description=summary_data.detailed_description,
            main_topics=summary_data.main_topics,
            purpose=summary_data.purpose,
            audience=summary_data.audience,
            components=components,
            metadata={
                "created_datetime": site_info.get("createdDateTime", ""),
                "web_url": site_info.get("webUrl", ""),
                "list_count": len(lists),
                "library_count": len(libraries)
            },
            confidence_score=summary_data.confidence
        )
        
        self._cache[cache_key] = analysis
        return analysis
    
    async def analyze_page(self, site_id: str, page_id: str) -> ContentAnalysis:
        """Analyze a SharePoint page to understand its content and purpose.
        
        Args:
            site_id: SharePoint site ID
            page_id: Page ID
            
        Returns:
            ContentAnalysis with page understanding
        """
        cache_key = f"page_{site_id}_{page_id}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if (datetime.now().timestamp() - cached.analyzed_at) < self._cache_ttl:
                return cached
        
        # Get page information
        page_info = await self.page_service.get_page_by_id(site_id, page_id)
        
        if not page_info:
            return ContentAnalysis(
                resource_type="page",
                resource_id=page_id,
                resource_name="Unknown Page",
                summary="Page not found or could not be retrieved",
                detailed_description="Unable to analyze this page",
                confidence_score=0.0
            )
        
        # Parse page content
        page_name = page_info.get("name", "Unknown Page")
        page_title = page_info.get("title", page_name)
        canvas_content = page_info.get("canvasContent1", "")
        
        # Extract web parts and text content
        components, text_content = self._parse_page_canvas(canvas_content)
        
        # Build context for AI analysis
        context = self._build_page_context(page_info, components, text_content)
        
        # Get AI summary
        summary_data = await self._generate_ai_summary(
            resource_type="page",
            resource_name=page_title,
            context=context
        )
        
        # Build ContentAnalysis
        analysis = ContentAnalysis(
            resource_type="page",
            resource_id=page_id,
            resource_name=page_title,
            summary=summary_data.summary,
            detailed_description=summary_data.detailed_description,
            main_topics=summary_data.main_topics,
            purpose=summary_data.purpose,
            audience=summary_data.audience,
            components=components,
            metadata={
                "page_layout": page_info.get("pageLayout", ""),
                "web_url": page_info.get("webUrl", ""),
                "created_datetime": page_info.get("createdDateTime", ""),
                "last_modified": page_info.get("lastModifiedDateTime", ""),
                "web_part_count": len(components)
            },
            confidence_score=summary_data.confidence
        )
        
        self._cache[cache_key] = analysis
        return analysis
    
    async def analyze_list(self, site_id: str, list_id: str) -> ContentAnalysis:
        """Analyze a SharePoint list to understand its purpose.
        
        Args:
            site_id: SharePoint site ID
            list_id: List ID
            
        Returns:
            ContentAnalysis with list understanding
        """
        cache_key = f"list_{site_id}_{list_id}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if (datetime.now().timestamp() - cached.analyzed_at) < self._cache_ttl:
                return cached
        
        # Get list information directly via graph_client
        list_info = None
        try:
            list_info = await self.graph_client.get(f"/sites/{site_id}/lists/{list_id}")
        except Exception:
            pass
        
        if not list_info:
            return ContentAnalysis(
                resource_type="list",
                resource_id=list_id,
                resource_name="Unknown List",
                summary="List not found or could not be retrieved",
                detailed_description="Unable to analyze this list",
                confidence_score=0.0
            )
        
        list_name = list_info.get("displayName", "Unknown List")
        # Detect the true resource type from the list's template
        template = list_info.get("list", {}).get("template", "")
        detected_type = "library" if template == "documentLibrary" else "list"
        
        # Get columns
        columns_response = await self.graph_client.get(
            f"/sites/{site_id}/lists/{list_id}/columns"
        )
        columns = columns_response.get("value", []) if columns_response else []
        
        # Get sample items (first 10 for richer AI context)
        items_response = await self.graph_client.get(
            f"/sites/{site_id}/lists/{list_id}/items?$expand=fields&$top=10"
        )
        items = items_response.get("value", []) if items_response else []
        
        # Build components (columns)
        components = []
        for col in columns:
            if not col.get("hidden", False) and not col.get("readOnly", False):
                components.append({
                    "type": "column",
                    "name": col.get("displayName", col.get("name", "Unknown")),
                    "column_type": self._get_column_type(col),
                    "required": col.get("required", False)
                })
        
        # For document libraries: use indexed file content for a richer analysis
        if detected_type == "library":
            from src.infrastructure.services.document_index import DocumentIndexService
            indexed_docs = await DocumentIndexService().get_library_documents(list_id)
            # If no indexed docs but files exist in SharePoint, parse them on the fly
            if not indexed_docs and items:
                live_docs = await self._fetch_and_parse_library_files(list_id, max_files=10)
            else:
                live_docs = []
            context = self._build_library_content_context(
                list_info, columns, items, indexed_docs[:10] or live_docs
            )
        else:
            context = self._build_list_context(list_info, columns, items)
        
        # Get AI summary — pass the real resource type so the AI says "library" not "list"
        summary_data = await self._generate_ai_summary(
            resource_type=detected_type,
            resource_name=list_name,
            context=context
        )
        
        # Build ContentAnalysis
        analysis = ContentAnalysis(
            resource_type=detected_type,
            resource_id=list_id,
            resource_name=list_name,
            summary=summary_data.summary,
            detailed_description=summary_data.detailed_description,
            main_topics=summary_data.main_topics,
            purpose=summary_data.purpose,
            audience=summary_data.audience,
            components=components,
            suggested_actions=summary_data.suggested_actions,
            metadata={
                "description": list_info.get("description", ""),
                "item_count": list_info.get("list", {}).get("itemCount", 0),
                "created_datetime": list_info.get("createdDateTime", ""),
                "last_modified": list_info.get("lastModifiedDateTime", ""),
                "column_count": len(components)
            },
            confidence_score=summary_data.confidence
        )
        
        self._cache[cache_key] = analysis
        return analysis
    
    async def _get_site_info(self, site_id: str) -> Dict[str, Any]:
        """Get basic site information."""
        try:
            site = await self.graph_client.get(f"/sites/{site_id}")
            return site if site else {}
        except Exception:
            return {}
    
    def _build_site_context(self, site_info: Dict, lists: List[Dict], libraries: List[Dict]) -> str:
        """Build context text for site analysis."""
        context_parts = [
            f"Site Name: {site_info.get('displayName', 'Unknown')}",
            f"Description: {site_info.get('description', 'No description')}",
            f"\nLists ({len(lists)}):"
        ]
        
        for lst in lists[:10]:  # First 10 lists
            context_parts.append(f"  - {lst.get('displayName', 'Unknown')}: {lst.get('description', '')}")
        
        context_parts.append(f"\nLibraries ({len(libraries)}):")
        for lib in libraries[:10]:  # First 10 libraries
            context_parts.append(f"  - {lib.get('name', 'Unknown')}: {lib.get('description', '')}")
        
        return "\n".join(context_parts)
    
    def _build_page_context(self, page_info: Dict, components: List[Dict], text_content: str) -> str:
        """Build context text for page analysis."""
        context_parts = [
            f"Page Title: {page_info.get('title', 'Unknown')}",
            f"Layout: {page_info.get('pageLayout', 'Unknown')}",
            f"\nWeb Parts ({len(components)}):"
        ]
        
        for comp in components:
            context_parts.append(f"  - {comp['type']}: {comp.get('title', 'Untitled')}")
        
        if text_content:
            context_parts.append(f"\nText Content Preview:\n{text_content[:500]}")
        
        return "\n".join(context_parts)
    
    async def _fetch_and_parse_library_files(self, library_id: str, max_files: int = 10) -> List[Dict]:
        """Download and parse up to max_files from a SharePoint library on-the-fly."""
        from src.infrastructure.services.sharepoint.drive_service import DriveService
        from src.infrastructure.services.document_parser import DocumentParserService
        drive_service = DriveService(self.graph_client)
        parser = DocumentParserService()
        results = []
        try:
            all_items = await drive_service.get_library_items(library_id)
            # Only attempt parseable types
            parseable_exts = {'.docx', '.pdf', '.txt', '.csv', '.xlsx'}
            candidates = [
                it for it in all_items
                if any(str(it.name or '').lower().endswith(ext) for ext in parseable_exts)
            ][:max_files]
            if not candidates:
                return results
            # Reuse drive_id from the first item (already populated by get_library_items)
            drive_id = candidates[0].drive_id or await drive_service.get_library_drive_id(library_id)
            for lib_item in candidates:
                try:
                    file_bytes = await drive_service.download_file(lib_item.item_id, drive_id)
                    ext = '.' + lib_item.name.rsplit('.', 1)[-1].lower() if '.' in lib_item.name else ''
                    parsed = await parser.parse_document(file_bytes, lib_item.name, ext)
                    results.append({
                        'file_id': lib_item.item_id,
                        'library_id': library_id,
                        'file_name': lib_item.name,
                        'file_type': ext,
                        'parsed_text': parsed.text,
                        'tables': parsed.get_tables_as_dict(),
                        'word_count': parsed.word_count,
                        'error': parsed.error,
                        'metadata': {},
                        'entities': {},
                    })
                except Exception as e:
                    logger.warning("Could not parse library file %s: %s", getattr(lib_item, 'name', '?'), e)
        except Exception as e:
            logger.warning("Could not fetch library files for analysis: %s", e)
        return results

    def _build_library_content_context(
        self, list_info: Dict, columns: List[Dict], items: List[Dict],
        indexed_docs: List[Dict]
    ) -> str:
        """Build context for a document library — uses actual indexed file content when available."""
        lib_name = list_info.get("displayName", "Unknown Library")
        item_count = list_info.get("list", {}).get("itemCount", 0)
        description = list_info.get("description", "").strip()

        parts = [
            f"Library Name: {lib_name}",
            f"Description: {description or 'No description provided'}",
            f"Total files stored: {item_count}",
        ]

        if indexed_docs:
            parts.append(f"\nFile content ({len(indexed_docs)} file(s) read and analysed):")
            for i, doc in enumerate(indexed_docs, 1):
                fname = doc.get("file_name", "Unknown file")
                ftype = doc.get("file_type", "")
                text = (doc.get("parsed_text") or "").strip()
                tables = doc.get("tables", [])
                parts.append(f"\n  File {i}: {fname} ({ftype})")
                if text:
                    # Include up to 600 chars of text per file
                    parts.append(f"    Content excerpt: {text[:600]}{'...' if len(text) > 600 else ''}")
                if tables:
                    parts.append(f"    Contains {len(tables)} table(s). First table preview:")
                    first_table = tables[0]
                    if isinstance(first_table, dict):
                        headers = first_table.get("headers", [])
                        rows = first_table.get("rows", [])[:3]
                        if headers:
                            parts.append(f"      Columns: {', '.join(str(h) for h in headers[:8])}")
                        for row in rows:
                            parts.append(f"      Row: {json.dumps(row, default=str)[:200]}")
        elif item_count == 0:
            parts.append(
                f"\nThis library is currently EMPTY — no files have been uploaded yet."
                f"\nINSTRUCTION: Since the library is empty, infer its purpose entirely from its name "
                f"'{lib_name}' and describe what kinds of documents it is designed to store, "
                f"who would use it, and what data those documents would typically contain."
            )
        else:
            # Files exist but content couldn't be parsed (unsupported format, etc.) — show file names
            parts.append(f"\nFiles in library (file names only — content could not be parsed):")
            for j, item in enumerate(items[:10], 1):
                fields = item.get("fields", {})
                fname = fields.get("FileLeafRef", fields.get("Title", f"File {j}"))
                size = fields.get("File_x0020_Size", "")
                modified = fields.get("Modified", "")
                parts.append(f"  {j}. {fname}" + (f" ({size} bytes)" if size else "") + (f" — last modified {modified}" if modified else ""))
            parts.append(
                "\nINSTRUCTION: The content inside the files could not be read. "
                "Describe the library based on the file names and what kind of data they likely contain, "
                "and mention that the user can ask you to read a specific file for full details."
            )

        return "\n".join(parts)

    def _build_list_context(self, list_info: Dict, columns: List[Dict], items: List[Dict]) -> str:
        """Build context text for list analysis."""
        context_parts = [
            f"List Name: {list_info.get('displayName', 'Unknown')}",
            f"Description: {list_info.get('description', 'No description')}",
            f"Item Count: {list_info.get('list', {}).get('itemCount', 0)}",
            f"\nColumns:"
        ]
        
        for col in columns[:15]:
            if not col.get("hidden", False):
                col_name = col.get("displayName", col.get("name", "Unknown"))
                col_type = self._get_column_type(col)
                context_parts.append(f"  - {col_name} ({col_type})")
        
        if items:
            context_parts.append(f"\nActual items in the list (use these to describe the real content):")
            for i, item in enumerate(items[:5], 1):
                fields = item.get("fields", {})
                # Filter out system fields for readability
                user_fields = {
                    k: v for k, v in fields.items()
                    if not k.startswith(("@", "_", "OData", "Editor", "Author",
                                         "ContentType", "Attachments", "Edit",
                                         "LinkTitle", "DocIcon"))
                    and v not in (None, "", [], {})
                }
                context_parts.append(f"  Item {i}: {json.dumps(user_fields, default=str)[:300]}")
        else:
            context_parts.append("\nNo items found in this list yet.")

        return "\n".join(context_parts)
    
    def _parse_page_canvas(self, canvas_content: str) -> tuple[List[Dict], str]:
        """Parse page canvas JSON to extract web parts and text.
        
        Returns:
            Tuple of (components list, text_content string)
        """
        components = []
        text_parts = []
        
        if not canvas_content:
            return components, ""
        
        try:
            canvas_data = json.loads(canvas_content) if isinstance(canvas_content, str) else canvas_content
            
            for control in canvas_data:
                web_part_type = control.get("webPartType", "Unknown")
                components.append({
                    "type": "web_part",
                    "web_part_type": web_part_type,
                    "title": control.get("title", ""),
                    "id": control.get("id", "")
                })
                
                # Extract text from TextWebPart
                if web_part_type == "TextWebPart":
                    data = control.get("webPartData", {})
                    if isinstance(data, dict):
                        text = data.get("innerHTML", "") or data.get("text", "")
                        if text:
                            text_parts.append(text)
        
        except Exception as e:
            logger.warning(f"Could not parse canvas content: {e}")
        
        return components, " ".join(text_parts)
    
    def _get_column_type(self, column: Dict) -> str:
        """Extract column type from column definition."""
        if "text" in column:
            return "text"
        elif "number" in column:
            return "number"
        elif "dateTime" in column:
            return "dateTime"
        elif "choice" in column:
            return "choice"
        elif "lookup" in column:
            return "lookup"
        elif "boolean" in column:
            return "boolean"
        elif "personOrGroup" in column:
            return "personOrGroup"
        else:
            return "unknown"
    
    async def _generate_ai_summary(self, resource_type: str, resource_name: str, context: str) -> ContentSummary:
        """Use AI to generate intelligent summary of resource.
        
        Args:
            resource_type: Type of resource (site, page, list)
            resource_name: Name of the resource
            context: Context information for analysis
            
        Returns:
            ContentSummary with AI-generated insights
        """
        try:
            client, model = get_instructor_client()
            
            is_library = resource_type == "library"
            library_guidance = (
                "\n\nSPECIAL INSTRUCTIONS FOR DOCUMENT LIBRARY:"
                "\n- If the context says the library is EMPTY: describe what it is DESIGNED FOR based on the name. "
                "Say it is currently empty and explain what types of documents should be uploaded."
                "\n- If the context includes INDEXED FILE CONTENT: summarise the actual content of those files. "
                "Mention specific data found (e.g. salary figures, employee names, dates) and what insights can be drawn."
                "\n- If the context has file names only (no content): describe what those files likely contain based on their names."
                "\n- Do NOT describe the column structure (Created, Modified, etc.) as the main content — those are just metadata."
            ) if is_library else ""

            prompt = f"""You are analyzing a SharePoint {resource_type} called "{resource_name}".

Context data:
{context}
{library_guidance}

You MUST fill in each field below with REAL TEXT based on the context above.
DO NOT return JSON schema definitions, type names, or field descriptions.
DO NOT say "string" or "List[str]" — write actual sentences and words.

Fill in these fields with real values:
- summary: Write 2-3 actual sentences describing what {resource_name} is used for (or contains, if files were read)
- detailed_description: Write a paragraph describing the actual content — for libraries, focus on what the files contain or what the library is designed to store
- main_topics: List 3-8 actual topic keywords
- purpose: Write one sentence stating the business purpose
- audience: Write who uses this
- confidence: Write a number between 0.0 and 1.0
- suggested_actions: List 3 specific natural-language commands relevant to this library/list

IMPORTANT: Be specific and concrete. For libraries with file content, mention actual data found in the files."""

            create_kwargs = {
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that describes SharePoint list contents in plain, friendly language. Focus on what the data actually contains."},
                    {"role": "user", "content": prompt}
                ],
                "response_model": ContentSummary,
                "max_retries": 2,
            }
            if model:  # Only pass model for non-Gemini providers
                create_kwargs["model"] = model
            # The instructor client is synchronous — run it in a thread to avoid
            # blocking the event loop and the 'can't be used in await' error.
            response = await asyncio.to_thread(
                functools.partial(client.chat.completions.create, **create_kwargs)
            )
            
            return response
        
        except Exception as e:
            logger.warning(f"AI summary generation failed: {e}")
            # Build a useful fallback from the context text instead of generic strings
            # Extract any column/item hints from context for smarter fallback
            context_lines = context.strip().splitlines() if context else []
            topic_hints = [
                line.strip().lstrip('-•* ').split(':')[0].strip()
                for line in context_lines
                if line.strip() and len(line.strip()) < 60 and ':' in line
            ][:6] or [resource_name.lower(), resource_type]
            return ContentSummary(
                summary=f"'{resource_name}' is a SharePoint {resource_type} that stores and manages related data and documents.",
                detailed_description=(
                    f"The '{resource_name}' {resource_type} contains structured data with "
                    + (f"{len(context_lines)} detected fields/items. " if context_lines else "")
                    + "It is used to organise and track information relevant to your team or project."
                ),
                main_topics=topic_hints,
                purpose=f"Store and manage {resource_name.lower()} related data",
                audience="Team members and project stakeholders",
                confidence=0.2
            )
