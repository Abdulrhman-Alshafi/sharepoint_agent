"""Service for library intelligence operations - comparison, summarization, and analysis."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class LibrarySummary(BaseModel):
    """Summary of a document library."""
    library_name: str = Field(description="Name of the library")
    library_id: str = Field(description="ID of the library")
    total_files: int = Field(description="Total number of files")
    file_type_distribution: Dict[str, int] = Field(description="Distribution of file types")
    total_size_mb: float = Field(default=0.0, description="Total size in MB")
    main_themes: List[str] = Field(default_factory=list, description="Main content themes")
    summary: str = Field(description="AI-generated summary of library purpose and content")
    indexed_files: int = Field(default=0, description="Number of files with parsed content")
    key_statistics: Dict[str, Any] = Field(default_factory=dict, description="Additional statistics")


class LibraryComparison(BaseModel):
    """Comparison between two or more libraries."""
    libraries: List[str] = Field(description="Names of libraries being compared")
    comparison_aspects: Dict[str, Any] = Field(description="Comparison across different aspects")
    similarities: List[str] = Field(default_factory=list, description="Common elements")
    differences: List[str] = Field(default_factory=list, description="Key differences")
    recommendation: str = Field(default="", description="Recommendation or insight")


class LibraryIntelligenceService:
    """Service for intelligent library analysis and comparison."""
    
    def __init__(self):
        """Initialize library intelligence service."""
        self.client, self.model = get_instructor_client()
    
    async def summarize_library(
        self,
        library_name: str,
        library_id: str,
        file_items: List[Any],
        indexed_docs: List[Dict[str, Any]],
        library_stats: Dict[str, Any]
    ) -> LibrarySummary:
        """Generate comprehensive summary of a library.
        
        Args:
            library_name: Name of the library
            library_id: Library ID
            file_items: List of LibraryItem objects from repository
            indexed_docs: List of indexed/parsed documents
            library_stats: Statistics from document index
            
        Returns:
            LibrarySummary with analysis
        """
        # Calculate file type distribution from items
        file_types = {}
        total_size = 0.0
        
        for item in file_items:
            file_type = item.file_type or 'unknown'
            file_types[file_type] = file_types.get(file_type, 0) + 1
            total_size += item.size_mb
        
        # Extract themes from indexed documents if available
        themes = []
        if indexed_docs:
            themes = await self._extract_themes_from_docs(indexed_docs)
        
        # Generate AI summary
        summary_text = await self._generate_library_summary(
            library_name,
            len(file_items),
            file_types,
            indexed_docs[:5] if indexed_docs else []  # Sample of docs
        )
        
        return LibrarySummary(
            library_name=library_name,
            library_id=library_id,
            total_files=len(file_items),
            file_type_distribution=file_types,
            total_size_mb=round(total_size, 2),
            main_themes=themes,
            summary=summary_text,
            indexed_files=len(indexed_docs),
            key_statistics=library_stats
        )
    
    async def compare_libraries(
        self,
        libraries_data: List[Dict[str, Any]]
    ) -> LibraryComparison:
        """Compare multiple libraries across various dimensions.
        
        Args:
            libraries_data: List of dicts with library summaries and metadata
            
        Returns:
            LibraryComparison with detailed comparison
        """
        if len(libraries_data) < 2:
            return LibraryComparison(
                libraries=[lib.get('name', 'Unknown') for lib in libraries_data],
                comparison_aspects={},
                similarities=[],
                differences=["Need at least 2 libraries to compare"],
                recommendation="Please provide at least two libraries for comparison."
            )
        
        library_names = [lib.get('name', 'Unknown') for lib in libraries_data]
        
        # Build comparison across multiple aspects
        comparison_aspects = {
            "file_count": {
                lib.get('name'): lib.get('file_count', 0)
                for lib in libraries_data
            },
            "file_types": {
                lib.get('name'): lib.get('file_types', {})
                for lib in libraries_data
            },
            "themes": {
                lib.get('name'): lib.get('themes', [])
                for lib in libraries_data
            },
            "size_mb": {
                lib.get('name'): lib.get('size_mb', 0)
                for lib in libraries_data
            }
        }
        
        # Use AI to generate insights
        comparison_insight = await self._generate_comparison_insight(
            library_names,
            comparison_aspects
        )
        
        return LibraryComparison(
            libraries=library_names,
            comparison_aspects=comparison_aspects,
            similarities=comparison_insight.get('similarities', []),
            differences=comparison_insight.get('differences', []),
            recommendation=comparison_insight.get('recommendation', '')
        )
    
    async def _extract_themes_from_docs(
        self, indexed_docs: List[Dict[str, Any]]
    ) -> List[str]:
        """Extract main themes from indexed documents.
        
        Args:
            indexed_docs: List of indexed documents
            
        Returns:
            List of theme strings
        """
        if not indexed_docs:
            return []
        
        # Collect categories/entities from docs
        all_categories = []
        for doc in indexed_docs[:20]:  # Limit to 20 docs
            entities = doc.get('entities', {})
            if isinstance(entities, dict) and 'categories' in entities:
                all_categories.extend(entities.get('categories', []))
        
        # Get unique themes
        unique_themes = list(set(all_categories))[:10]  # Top 10
        
        return unique_themes if unique_themes else ["General Documents"]
    
    async def _generate_library_summary(
        self,
        library_name: str,
        file_count: int,
        file_types: Dict[str, int],
        sample_docs: List[Dict[str, Any]]
    ) -> str:
        """Generate AI summary of library purpose and content.
        
        Args:
            library_name: Library name
            file_count: Number of files
            file_types: File type distribution
            sample_docs: Sample of indexed documents
            
        Returns:
            Summary text
        """
        # Build prompt
        prompt = f"""Analyze this SharePoint document library and provide a 2-3 sentence summary:

**Library Name:** {library_name}
**Total Files:** {file_count}
**File Types:** {', '.join([f'{k}: {v}' for k, v in file_types.items()])}
"""
        
        if sample_docs:
            prompt += "\n**Sample Documents:**\n"
            for doc in sample_docs[:3]:
                file_name = doc.get('file_name', 'Unknown')
                entities = doc.get('entities', {})
                summary = entities.get('summary', '') if isinstance(entities, dict) else ''
                prompt += f"- {file_name}: {summary[:100] if summary else 'No summary'}\n"
        
        prompt += "\n\nWrite a concise 2-sentence summary (max 60 words) covering: (1) what this library stores/is used for, (2) who would use it. Be direct and professional. Do NOT repeat the library name more than once. Do NOT list column names."
        
        try:
            # Generate summary using AI
            active_model = self.model or "gemini-1.5-flash"
            response = self.client.chat.completions.create(
                model=active_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Error generating library summary: {e}")
            return f"Library containing {file_count} files of various types."
    
    async def _generate_comparison_insight(
        self,
        library_names: List[str],
        comparison_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate AI insights from library comparison.
        
        Args:
            library_names: Names of libraries
            comparison_data: Comparison aspects dict
            
        Returns:
            Dict with similarities, differences, and recommendations
        """
        prompt = f"""Compare these SharePoint document libraries and identify key insights:

**Libraries:** {', '.join(library_names)}

**Comparison Data:**
"""
        
        for aspect, data in comparison_data.items():
            prompt += f"\n**{aspect.replace('_', ' ').title()}:**\n"
            for lib, value in data.items():
                prompt += f"  - {lib}: {value}\n"
        
        prompt += """
Provide:
1. Similarities (2-3 points)
2. Key differences (2-3 points)
3. A recommendation or insight (1-2 sentences)

Format as JSON with keys: similarities (list), differences (list), recommendation (string)"""
        
        try:
            # Use AI to generate insights
            active_model = self.model or "gemini-1.5-flash"
            response = self.client.chat.completions.create(
                model=active_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            import json
            result_text = response.choices[0].message.content.strip()

            # Try to parse JSON
            try:
                if result_text.startswith("```json"):
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                return json.loads(result_text)
            except Exception:
                # Fallback to text parsing
                return {
                    'similarities': [result_text],
                    'differences': [],
                    'recommendation': "See analysis above."
                }

        except Exception as e:
            logger.error(f"Error generating comparison insight: {e}")
            return {
                'similarities': ["Both are SharePoint document libraries"],
                'differences': ["Different file counts and types"],
                'recommendation': f"Error generating insights: {str(e)}"
            }
