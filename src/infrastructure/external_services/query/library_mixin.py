"""Mixin providing library and document query handlers for AIDataQueryService."""

import logging
import re
from typing import List, Optional

from src.domain.entities import DataQueryResult
from src.domain.value_objects.resource_candidate import ResourceCandidate

logger = logging.getLogger(__name__)


class LibraryQueryMixin:
    """Handlers for library_content, document_search, data_extraction,
    library_comparison, content_summary, and search queries.

    Requires *self* to provide:
        self.sharepoint_repository
        self.document_index       – DocumentIndexService
        self.document_intelligence – DocumentIntelligenceService
        self.library_intelligence  – LibraryIntelligenceService
        self.search_service        – SearchService
    """

    async def _handle_library_content_query(
        self,
        question: str,
        library_id: str,
        library_name: str,
        site_id: str = None,
        site_name: str = None,
        resource_web_url: str = None,
        sibling_resources: Optional[List[ResourceCandidate]] = None,
    ) -> DataQueryResult:
        """Handle queries about files in a library.

        If the question is analytical (average, sum, total, calculate, how much…)
        it is delegated to ``_handle_data_extraction_query`` which reads actual
        parsed document content instead of just listing file metadata.
        """
        # ── Analytical-query redirect ──────────────────────────────────
        _ANALYTICAL_KEYWORDS = {
            "average", "avg", "mean", "sum", "total", "maximum", "minimum",
            "max", "min", "highest", "lowest", "calculate", "how much",
            "salary", "salaries", "pay", "payroll", "net", "gross", "earn",
            "income", "wage", "wages", "cost", "costs", "budget", "price",
            "amount", "count items", "aggregate",
        }
        question_lower = question.lower()
        is_analytical = any(kw in question_lower for kw in _ANALYTICAL_KEYWORDS)
        if is_analytical:
            logger.info(
                "Analytical question detected for library '%s' — delegating to data_extraction",
                library_name,
            )
            return await self._handle_data_extraction_query(
                question, library_id, library_name
            )
        # ────────────────────────────────────────────────────────────────
        try:
            file_items = await self.sharepoint_repository.get_library_items(library_id, site_id=site_id)
            site_context = f" in the **{site_name}** site" if site_name else ""

            if not file_items:
                return DataQueryResult(
                    answer=f"The **{library_name}** library{site_context} is currently empty.",
                    suggested_actions=[
                        f"Upload a file to {library_name}",
                        "Show me all libraries",
                        "Create a new document library",
                    ],
                )

            indexed_docs = await self.document_index.get_library_documents(library_id)

            file_list = []
            for i, item in enumerate(file_items[:50], 1):
                size = (
                    f"({item.size_mb:.2f} MB)" if item.size_mb >= 0.01 else f"({item.size} bytes)"
                )
                file_list.append(f"{i}. **{item.name}** {size}")

            answer = (
                f"**{library_name}** library{site_context} contains **{len(file_items)}** file(s):\n\n"
                + "\n".join(file_list)
            )
            if len(file_items) > 50:
                answer += f"\n... and {len(file_items) - 50} more files."
            answer += f"\n\n📊 **{len(indexed_docs)}** files have been analyzed and indexed for content search."

            # Phase 13: mention sibling libraries if discovered
            if sibling_resources:
                _sib_names = ", ".join(f"**{s.title}**" for s in sibling_resources[:3])
                answer += f"\n\nRelated libraries you may also want to explore: {_sib_names}."

            return DataQueryResult(
                answer=answer,
                data_summary={
                    "file_count": len(file_items),
                    "indexed_count": len(indexed_docs),
                    "sibling_libraries_included": [s.title for s in (sibling_resources or [])],
                },
                source_list=library_name,
                resource_link=resource_web_url or "",
                suggested_actions=[
                    f"Analyze content in {library_name}",
                    f"Upload a file to {library_name}",
                    "Compare this library with another",
                ],
            )
        except Exception as exc:
            logger.error("Failed to query library content: %s", exc)
            return DataQueryResult(
                answer=f"I encountered an error accessing the {library_name} library: {exc}",
                suggested_actions=["Show me all libraries"],
            )

    async def _handle_document_search_query(
        self, search_query: str, library_id: str = None
    ) -> DataQueryResult:
        """Handle document search queries."""
        try:
            results = await self.document_index.search_documents(search_query, library_id)
            if not results:
                return DataQueryResult(
                    answer=f"No documents found matching '{search_query}'.",
                    suggested_actions=[
                        "Show me all libraries",
                        "Upload a document",
                        "Index library documents",
                    ],
                )

            result_list = []
            for i, doc in enumerate(results[:20], 1):
                file_name = doc.get("file_name", "Unknown")
                snippet = (doc.get("parsed_text", "")[:100] + "...") if doc.get("parsed_text") else ""
                result_list.append(f"{i}. **{file_name}**\n   {snippet}")

            answer = f"Found **{len(results)}** document(s) matching '{search_query}':\n\n"
            answer += "\n\n".join(result_list)
            if len(results) > 20:
                answer += f"\n\n... and {len(results) - 20} more results."

            return DataQueryResult(
                answer=answer,
                data_summary={"result_count": len(results)},
                suggested_actions=[
                    "Show me more details about the first document",
                    "Refine my search",
                    "Search in a specific library",
                ],
            )
        except Exception as exc:
            logger.error("Failed to search documents: %s", exc)
            return DataQueryResult(
                answer=f"I encountered an error searching documents: {exc}",
                suggested_actions=["Show me all libraries"],
            )

    async def _handle_data_extraction_query(
        self, data_query: str, library_id: str = None, library_name: str = None
    ) -> DataQueryResult:
        """Handle data extraction queries from document content.

        If no pre-indexed documents exist in the local SQLite index, this method
        will automatically download, parse, and index the library's files from
        SharePoint on-the-fly so the user's question can be answered immediately.
        """
        try:
            if library_id:
                indexed_docs = await self.document_index.get_library_documents(library_id)
            else:
                indexed_docs = await self.document_index.search_documents("", None)

            # ── Live fetch fallback: download & parse files from SharePoint ──
            if not indexed_docs and library_id:
                logger.info(
                    "No indexed docs for library '%s' — fetching and parsing files live from SharePoint",
                    library_name or library_id,
                )
                live_docs, is_background, est_secs = await self._fetch_and_parse_library_files(library_id)
                
                if is_background:
                    mins = max(1, est_secs // 60)
                    lib_label = f"**{library_name}**" if library_name else "This library"
                    return DataQueryResult(
                        answer=(
                            f"{lib_label} contains many un-indexed files. I have started reading and indexing them in the background.\n\n"
                            f"⏱️ **Estimated time:** {mins} minute{'s' if mins > 1 else ''}\n\n"
                            f"Please wait a moment and then ask your question again. You can continue chatting with me in the meantime!"
                        ),
                        suggested_actions=[data_query, "Show me all libraries"],
                        source_list=library_name,
                    )

                if live_docs:
                    indexed_docs = live_docs
                    logger.info(
                        "Live-parsed %d file(s) from library '%s'",
                        len(live_docs), library_name or library_id,
                    )

            if not indexed_docs:
                lib_label = f"**{library_name}**" if library_name else "This document library"
                upload_action = f"Upload a document to {library_name}" if library_name else "Upload a document"
                return DataQueryResult(
                    answer=(
                        f"{lib_label} is empty — there are no documents uploaded yet, "
                        f"so I can't answer questions about its content.\n\n"
                        f"To get data (like average salaries, totals, or summaries), "
                        f"upload the relevant files (Excel, PDF, Word, etc.) to {lib_label} first. "
                        f"Once they're uploaded, I can read and analyze their contents."
                    ),
                    suggested_actions=[
                        upload_action,
                        "Show me all libraries",
                        "Show me all lists",
                    ],
                )

            # ── Top-K filtering: score docs by keyword relevance (top 10) ──
            _TOP_K_DOCS = 10
            _keywords = [w for w in data_query.lower().split() if len(w) > 3]
            if _keywords and len(indexed_docs) > _TOP_K_DOCS:
                def _doc_score(doc: dict) -> int:
                    search_str = (
                        doc.get("file_name", "") + " " + doc.get("parsed_text", "")[:200]
                    ).lower()
                    return sum(1 for kw in _keywords if kw in search_str)
                indexed_docs = sorted(indexed_docs, key=_doc_score, reverse=True)[:_TOP_K_DOCS]
                _doc_prefix = f"Showing {len(indexed_docs)} most relevant documents.\n\n"
            else:
                _doc_prefix = ""

            _effective_query = _doc_prefix + data_query if _doc_prefix else data_query
            result = await self.document_intelligence.answer_data_query(
                _effective_query, indexed_docs, context=library_name,
            )
            return DataQueryResult(
                answer=result.answer,
                data_summary={
                    "confidence": result.confidence,
                    "sources": result.sources,
                    "supporting_data": result.supporting_data,
                },
                source_list=library_name,
                suggested_actions=[
                    f"Show me all files in {library_name}" if library_name else "Show me the source documents",
                    "Extract more data from these documents",
                    "Upload more documents for analysis",
                ],
            )
        except Exception as exc:
            logger.error("Failed to extract data from documents: %s", exc)
            return DataQueryResult(
                answer=f"I encountered an error analyzing document content: {exc}",
                suggested_actions=["Show me all libraries", "Try a simpler query"],
            )

    async def _fetch_and_parse_library_files(
        self, library_id: str, max_files: int = 1000
    ) -> tuple[list, bool, int]:
        """Download, parse, and auto-index files from a SharePoint library.

        If there are more than 10 files, this spawns a background task to process
        them and immediately returns indicating a background job was started.

        Returns:
            Tuple of (results_list, is_background_job, estimated_seconds)
        """
        import asyncio
        from src.infrastructure.services.sharepoint.drive_service import DriveService
        from src.infrastructure.services.document_parser import DocumentParserService

        drive_service = DriveService(self.graph_client)
        parser = DocumentParserService()
        results: list = []

        try:
            all_items = await drive_service.get_library_items(library_id)
            parseable_exts = {".docx", ".pdf", ".txt", ".csv", ".xlsx"}
            candidates = [
                item
                for item in all_items
                if any(
                    str(item.name or "").lower().endswith(ext)
                    for ext in parseable_exts
                )
            ][:max_files]

            if not candidates:
                logger.info("No parseable files found in library %s", library_id)
                return results, False, 0

            total_size_bytes = 0
            estimated_seconds = 0.0

            for item in candidates:
                item_size = getattr(item, "size", 0)
                total_size_bytes += item_size
                size_mb = item_size / (1024 * 1024)
                
                # 3 seconds base API overhead per file
                item_time = 3.0
                
                # Per-file-type processing weight (seconds per MB)
                name_lower = str(getattr(item, "name", "")).lower()
                if name_lower.endswith(".pdf"):
                    item_time += size_mb * 20.0  # OCR/pdfplumber is slow
                elif name_lower.endswith(".docx"):
                    item_time += size_mb * 5.0   # XML parsing is moderate
                elif name_lower.endswith(".xlsx") or name_lower.endswith(".xls"):
                    item_time += size_mb * 10.0  # Large sheets can be slow
                elif name_lower.endswith(".csv") or name_lower.endswith(".txt"):
                    item_time += size_mb * 1.0   # Plain text is extremely fast
                else:
                    item_time += size_mb * 10.0  # Fallback

                estimated_seconds += item_time

            total_size_mb = total_size_bytes / (1024 * 1024)

            # Offload to background if total size > 5MB or if there are >50 files (API rate limits)
            if total_size_mb > 5.0 or len(candidates) > 50:
                logger.info(
                    "Found %d files (%.2f MB). Offloading to background task.", 
                    len(candidates), total_size_mb
                )
                asyncio.create_task(self._process_candidates_background(candidates, library_id))
                return [], True, max(15, int(estimated_seconds))

            drive_id = (
                candidates[0].drive_id
                or await drive_service.get_library_drive_id(library_id)
            )

            for lib_item in candidates:
                try:
                    file_bytes = await drive_service.download_file(
                        lib_item.item_id, drive_id
                    )
                    ext = (
                        "." + lib_item.name.rsplit(".", 1)[-1].lower()
                        if "." in lib_item.name
                        else ""
                    )
                    parsed = await parser.parse_document(
                        file_bytes, lib_item.name, ext
                    )

                    doc_record = {
                        "file_id": lib_item.item_id,
                        "library_id": library_id,
                        "drive_id": drive_id,
                        "file_name": lib_item.name,
                        "file_type": ext,
                        "parsed_text": parsed.text,
                        "tables": parsed.get_tables_as_dict(),
                        "metadata": {},
                        "entities": {},
                        "word_count": parsed.word_count,
                        "error": parsed.error,
                    }
                    results.append(doc_record)

                    # Auto-index for future queries
                    try:
                        await self.document_index.index_document(
                            file_id=lib_item.item_id,
                            library_id=library_id,
                            drive_id=drive_id,
                            parsed_doc=parsed,
                            file_content=file_bytes,
                        )
                    except Exception as idx_err:
                        logger.warning(
                            "Auto-index failed for %s: %s",
                            lib_item.name, idx_err,
                        )

                except Exception as file_err:
                    logger.warning(
                        "Could not parse file %s: %s",
                        getattr(lib_item, "name", "?"), file_err,
                    )

        except Exception as exc:
            logger.warning(
                "Failed to fetch library files for live parsing: %s", exc
            )

        return results, False, 0

    async def _process_candidates_background(self, candidates: list, library_id: str):
        """Background task to download, parse, and index files."""
        from src.infrastructure.services.sharepoint.drive_service import DriveService
        from src.infrastructure.services.document_parser import DocumentParserService
        
        logger.info("Starting background indexing job for %d files in library %s", len(candidates), library_id)
        drive_service = DriveService(self.graph_client)
        parser = DocumentParserService()
        
        try:
            drive_id = candidates[0].drive_id or await drive_service.get_library_drive_id(library_id)
            
            for lib_item in candidates:
                try:
                    file_bytes = await drive_service.download_file(lib_item.item_id, drive_id)
                    ext = "." + lib_item.name.rsplit(".", 1)[-1].lower() if "." in lib_item.name else ""
                    parsed = await parser.parse_document(file_bytes, lib_item.name, ext)
                    
                    await self.document_index.index_document(
                        file_id=lib_item.item_id,
                        library_id=library_id,
                        drive_id=drive_id,
                        parsed_doc=parsed,
                        file_content=file_bytes,
                    )
                except Exception as file_err:
                    logger.warning("Background parse failed for %s: %s", getattr(lib_item, "name", "?"), file_err)
            
            logger.info("Successfully completed background indexing job for library %s", library_id)
        except Exception as exc:
            logger.error("Background indexing job failed: %s", exc)

    async def _handle_library_comparison_query(self, library_names: list) -> DataQueryResult:
        """Handle library comparison queries."""
        try:
            if len(library_names) < 2:
                return DataQueryResult(
                    answer="I need at least two library names to compare. Please specify which libraries you'd like to compare.",
                    suggested_actions=["Show me all libraries"],
                )

            all_libs = await self.sharepoint_repository.get_all_document_libraries()
            libraries_data = []
            for lib_name in library_names[:5]:
                matched_lib = next(
                    (lib for lib in all_libs if lib_name.lower() in lib.get("displayName", "").lower()),
                    None,
                )
                if matched_lib:
                    lib_id = matched_lib.get("id")
                    files = await self.sharepoint_repository.get_library_items(lib_id)
                    indexed = await self.document_index.get_library_documents(lib_id)
                    stats = await self.document_index.get_library_stats(lib_id)
                    libraries_data.append(
                        {
                            "name": matched_lib.get("displayName"),
                            "file_count": len(files),
                            "file_types": stats.get("file_type_distribution", {}),
                            "themes": [],
                            "size_mb": sum(f.size_mb for f in files),
                        }
                    )

            if not libraries_data:
                return DataQueryResult(
                    answer="I couldn't find the libraries you mentioned. Please check the names and try again.",
                    suggested_actions=["Show me all libraries"],
                )

            comparison = await self.library_intelligence.compare_libraries(libraries_data)
            answer = f"**Comparison of {', '.join(lib['name'] for lib in libraries_data)}:**\n\n"
            answer += "**File Counts:**\n"
            for name, count in comparison.comparison_aspects.get("file_count", {}).items():
                answer += f"• {name}: {count} files\n"
            answer += "\n**Similarities:**\n"
            for sim in comparison.similarities:
                answer += f"• {sim}\n"
            answer += "\n**Differences:**\n"
            for diff in comparison.differences:
                answer += f"• {diff}\n"
            if comparison.recommendation:
                answer += f"\n💡 **Recommendation:** {comparison.recommendation}"

            return DataQueryResult(
                answer=answer,
                data_summary={"comparison": comparison.comparison_aspects},
                suggested_actions=[
                    f"Show me files in {libraries_data[0]['name']}",
                    "Analyze content themes in these libraries",
                    "Create a summary report",
                ],
            )
        except Exception as exc:
            logger.error("Failed to compare libraries: %s", exc)
            return DataQueryResult(
                answer=f"I encountered an error comparing libraries: {exc}",
                suggested_actions=["Show me all libraries"],
            )

    async def _handle_content_summary_query(
        self, library_id: str, library_name: str
    ) -> DataQueryResult:
        """Handle library content summary queries."""
        try:
            file_items = await self.sharepoint_repository.get_library_items(library_id)
            indexed_docs = await self.document_index.get_library_documents(library_id)
            stats = await self.document_index.get_library_stats(library_id)

            summary = await self.library_intelligence.summarize_library(
                library_name, library_id, file_items, indexed_docs, stats
            )

            # ── Build a clean, readable summary ──────────────────────
            file_type_str = ", ".join(
                f"**{ft.upper()}** ({cnt})" for ft, cnt in summary.file_type_distribution.items()
            ) or "various formats"
            size_str = f"{summary.total_size_mb:.1f} MB" if summary.total_size_mb >= 0.1 else ""
            size_part = f" ({size_str})" if size_str else ""

            answer = f"## 📁 {summary.library_name}\n\n"
            answer += f"{summary.summary}\n\n"
            answer += "---\n"
            answer += f"**Files:** {summary.total_files}{size_part}  \n"
            answer += f"**Formats:** {file_type_str}  \n"
            if summary.indexed_files:
                answer += f"**Indexed for search:** {summary.indexed_files} file(s)  \n"
            if summary.main_themes:
                answer += f"**Topics:** {', '.join(summary.main_themes)}  \n"

            return DataQueryResult(
                answer=answer,
                data_summary={
                    "total_files": summary.total_files,
                    "file_types": summary.file_type_distribution,
                    "themes": summary.main_themes,
                },
                suggested_actions=[
                    f"Show me files in {library_name}",
                    f"Upload a file to {library_name}",
                    "Compare this library with another",
                ],
            )
        except Exception as exc:
            logger.error("Failed to summarize library: %s", exc)
            return DataQueryResult(
                answer=f"I encountered an error summarizing the library: {exc}",
                suggested_actions=["Show me all libraries"],
            )

    async def _handle_search_query(self, search_query: str) -> DataQueryResult:
        """Handle SharePoint-wide search queries."""
        try:
            results = await self.search_service.search_sharepoint(search_query)
            if not results:
                return DataQueryResult(
                    answer=f"No results found for '{search_query}' across SharePoint.",
                    suggested_actions=["Try a different search term", "Show me all libraries"],
                )

            answer = f"Found **{len(results)}** result(s) for '{search_query}':\n\n"
            for idx, hit in enumerate(results[:10], 1):
                resource = hit.get("resource", {})
                hit_summary = self._clean_search_snippet(hit.get("summary", ""))
                resource_name = (
                    resource.get("name")
                    or resource.get("title")
                    or resource.get("webUrl", "Unknown")
                )
                resource_name = self._clean_search_snippet(resource_name)
                resource_type = (
                    resource.get("@odata.type", "").split(".")[-1]
                    if resource.get("@odata.type")
                    else "item"
                )
                resource_url = resource.get("webUrl", "")
                answer += f"{idx}. **{resource_name}** ({resource_type})\n"
                if hit_summary:
                    answer += f"   {hit_summary}\n"
                if resource_url:
                    answer += f"   {resource_url}\n"
                answer += "\n"
            if len(results) > 10:
                answer += f"\n... and {len(results) - 10} more results."

            return DataQueryResult(
                answer=answer,
                data_summary={"result_count": len(results)},
                suggested_actions=[
                    "Show me more details",
                    "Search for something else",
                    "Show me all libraries",
                ],
            )
        except Exception as exc:
            logger.error("Failed to execute search: %s", exc)
            return DataQueryResult(
                answer=f"I encountered an error searching SharePoint: {exc}",
                suggested_actions=["Try again later", "Show me all lists"],
            )

    def _clean_search_snippet(self, text: str) -> str:
        """Normalize Graph search snippets for user-facing output.

        Graph can return highlight tags like <c0>..</c0> and separators like
        <ddd/> which are not suitable for end-user display.
        """
        if not text:
            return ""

        cleaned = str(text)
        # Remove Graph highlight markers and any HTML-like tags.
        cleaned = re.sub(r"</?c\d+>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<ddd\s*/?>", " … ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # De-duplicate repeated sentence fragments often returned by Graph snippets.
        parts = [p.strip() for p in re.split(r"\s+…\s+", cleaned) if p.strip()]
        if parts:
            deduped = []
            seen = set()
            for p in parts:
                key = p.lower()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(p)
            cleaned = " … ".join(deduped)

        return cleaned

    async def search_sharepoint(self, query: str, entity_types=None):
        """Perform a SharePoint-wide search using the SearchService."""
        return await self.search_service.search_sharepoint(query, entity_types)
