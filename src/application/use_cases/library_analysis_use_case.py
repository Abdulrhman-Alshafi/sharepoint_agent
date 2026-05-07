"""Library analysis use case for document library intelligence operations."""

import logging
from typing import List, Dict, Any
from src.domain.repositories import ILibraryRepository
from src.infrastructure.services.document_index import DocumentIndexService
from src.infrastructure.services.document_parser import DocumentParserService
from src.infrastructure.external_services.document_intelligence import DocumentIntelligenceService
from src.infrastructure.external_services.library_intelligence import LibraryIntelligenceService


class LibraryAnalysisUseCase:
    """Use case for library content analysis, comparison, and summarization."""

    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        sharepoint_repository: ILibraryRepository,
        document_index: DocumentIndexService,
        document_parser: DocumentParserService,
        document_intelligence: DocumentIntelligenceService,
        library_intelligence: LibraryIntelligenceService
    ):
        self.sharepoint_repository = sharepoint_repository
        self.document_index = document_index
        self.document_parser = document_parser
        self.document_intelligence = document_intelligence
        self.library_intelligence = library_intelligence

    async def summarize_library(self, library_id: str, library_name: str) -> Dict[str, Any]:
        """Generate comprehensive summary of a library.
        
        Args:
            library_id: ID of the library
            library_name: Name of the library
            
        Returns:
            Library summary dictionary
        """
        # Get library files
        file_items = await self.sharepoint_repository.get_library_items(library_id)
        
        # Get indexed documents
        indexed_docs = await self.document_index.get_library_documents(library_id)
        
        # Get library statistics
        stats = await self.document_index.get_library_stats(library_id)
        
        # Generate AI summary
        summary = await self.library_intelligence.summarize_library(
            library_name, library_id, file_items, indexed_docs, stats
        )
        
        return {
            "library_name": summary.library_name,
            "library_id": summary.library_id,
            "total_files": summary.total_files,
            "file_type_distribution": summary.file_type_distribution,
            "total_size_mb": summary.total_size_mb,
            "main_themes": summary.main_themes,
            "summary": summary.summary,
            "indexed_files": summary.indexed_files,
            "key_statistics": summary.key_statistics
        }

    async def compare_libraries(self, library_ids: List[str]) -> Dict[str, Any]:
        """Compare multiple libraries.
        
        Args:
            library_ids: List of library IDs to compare
            
        Returns:
            Comparison result dictionary
        """
        if len(library_ids) < 2:
            raise ValueError("At least 2 libraries required for comparison")
        
        # Get all libraries
        all_libs = await self.sharepoint_repository.get_all_document_libraries()
        
        # Build libraries data
        libraries_data = []
        missing_ids = []
        for lib_id in library_ids[:5]:  # Limit to 5
            # Find library info
            lib_info = next(
                (lib for lib in all_libs if lib.get('id') == lib_id),
                None
            )
            
            if not lib_info:
                missing_ids.append(lib_id)
                continue
            
            # Get files and stats
            files = await self.sharepoint_repository.get_library_items(lib_id)
            indexed = await self.document_index.get_library_documents(lib_id)
            stats = await self.document_index.get_library_stats(lib_id)
            
            # Extract themes from indexed docs
            themes = []
            if indexed:
                for doc in indexed[:10]:
                    entities = doc.get('entities', {})
                    if isinstance(entities, dict) and 'categories' in entities:
                        themes.extend(entities.get('categories', []))
            themes = list(set(themes))[:5]
            
            libraries_data.append({
                'name': lib_info.get('displayName'),
                'file_count': len(files),
                'file_types': stats.get('file_type_distribution', {}),
                'themes': themes,
                'size_mb': sum(f.size_mb for f in files)
            })
        
        # Generate comparison
        if missing_ids:
            raise ValueError(f"Libraries not found: {missing_ids}")

        comparison = await self.library_intelligence.compare_libraries(libraries_data)
        
        return {
            "libraries": comparison.libraries,
            "comparison_aspects": comparison.comparison_aspects,
            "similarities": comparison.similarities,
            "differences": comparison.differences,
            "recommendation": comparison.recommendation
        }

    async def search_library_content(
        self, library_id: str, search_query: str
    ) -> List[Dict[str, Any]]:
        """Search for documents within a library.
        
        Args:
            library_id: ID of the library
            search_query: Search query
            
        Returns:
            List of matching documents
        """
        results = await self.document_index.search_documents(search_query, library_id)
        
        return [
            {
                "file_id": doc.get('file_id'),
                "file_name": doc.get('file_name'),
                "file_type": doc.get('file_type'),
                "snippet": (lambda t: t[:200] + '...' if len(t) > 200 else t)(doc.get('parsed_text', '')),
                "word_count": doc.get('word_count'),
                "table_count": doc.get('table_count')
            }
            for doc in results
        ]

    async def extract_data_from_library(
        self, library_id: str, data_query: str
    ) -> Dict[str, Any]:
        """Extract specific data from library documents.
        
        Args:
            library_id: ID of the library
            data_query: Question to answer from document data
            
        Returns:
            Extraction result with answer and supporting data
        """
        # Get indexed documents
        indexed_docs = await self.document_index.get_library_documents(library_id)
        
        if not indexed_docs:
            return {
                "answer": "No indexed documents available in this library.",
                "confidence": "low",
                "sources": [],
                "supporting_data": []
            }
        
        # Use document intelligence to answer
        result = await self.document_intelligence.answer_data_query(
            data_query, indexed_docs
        )
        
        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "sources": result.sources,
            "supporting_data": result.supporting_data
        }

    async def analyze_document_themes(self, library_id: str) -> Dict[str, Any]:
        """Analyze themes across documents in a library.
        
        Args:
            library_id: ID of the library
            
        Returns:
            Theme analysis result
        """
        # Get indexed documents
        indexed_docs = await self.document_index.get_library_documents(library_id)
        
        if not indexed_docs:
            return {
                "themes": "No indexed documents available",
                "document_count": 0,
                "files_analyzed": []
            }
        
        # Convert to ParsedDocument objects
        from src.infrastructure.services.document_parser import ParsedDocument
        import pandas as pd
        
        parsed_docs = []
        for doc in indexed_docs[:20]:  # Analyze up to 20 docs
            # Reconstruct tables from JSON
            tables = []
            tables_json = doc.get('tables', [])
            if isinstance(tables_json, list):
                for table_data in tables_json:
                    if isinstance(table_data, list) and len(table_data) > 0:
                        try:
                            df = pd.DataFrame(table_data)
                            tables.append(df)
                        except Exception as e:
                            self._logger.warning("Table reconstruction failed for document '%s': %s", doc.get('file_name', '?'), e)
            
            parsed_doc = ParsedDocument(
                file_name=doc.get('file_name', ''),
                file_type=doc.get('file_type', ''),
                text=doc.get('parsed_text', ''),
                tables=tables,
                metadata=doc.get('metadata', {})
            )
            parsed_docs.append(parsed_doc)
        
        # Analyze themes
        analysis = await self.document_intelligence.analyze_document_theme(parsed_docs)
        
        return analysis

    async def get_library_statistics(self, library_id: str) -> Dict[str, Any]:
        """Get detailed statistics for a library.
        
        Args:
            library_id: ID of the library
            
        Returns:
            Library statistics
        """
        # Get files
        files = await self.sharepoint_repository.get_library_items(library_id)
        
        # Get index stats
        index_stats = await self.document_index.get_library_stats(library_id)
        
        # Calculate additional stats
        total_size = sum(f.size for f in files)
        parseable_count = sum(1 for f in files if f.is_parseable)
        
        file_types = {}
        for f in files:
            ft = f.file_type or 'unknown'
            file_types[ft] = file_types.get(ft, 0) + 1
        
        return {
            "total_files": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "parseable_files": parseable_count,
            "indexed_files": index_stats.get('total_documents', 0),
            "file_type_distribution": file_types,
            "total_words": index_stats.get('total_words', 0),
            "total_tables": index_stats.get('total_tables', 0),
            "unique_file_types": index_stats.get('unique_file_types', 0)
        }
