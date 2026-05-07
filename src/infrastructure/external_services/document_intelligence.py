"""Service for extracting structured entities from documents using AI."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.services.document_parser import ParsedDocument
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class MonetaryAmount(BaseModel):
    """Represents a monetary amount found in document."""
    amount: float = Field(description="Numeric value of the amount")
    currency: str = Field(default="USD", description="Currency code")
    context: str = Field(description="Context where amount was found (e.g., 'salary', 'expense', 'total')")


class PersonMention(BaseModel):
    """Represents a person mentioned in the document."""
    name: str = Field(description="Full name of the person")
    role: Optional[str] = Field(default=None, description="Role or title if mentioned")
    context: str = Field(description="Context of the mention")


class DateMention(BaseModel):
    """Represents a date mentioned in the document."""
    date_string: str = Field(description="Original date text from document")
    normalized_date: Optional[str] = Field(default=None, description="ISO format date if parseable")
    context: str = Field(description="Context of the date mention")


class DocumentEntities(BaseModel):
    """Structured entities extracted from a document."""
    monetary_amounts: List[MonetaryAmount] = Field(default_factory=list, description="All monetary amounts found")
    people: List[PersonMention] = Field(default_factory=list, description="All people mentioned")
    dates: List[DateMention] = Field(default_factory=list, description="All dates mentioned")
    categories: List[str] = Field(default_factory=list, description="Document categories or topics")
    key_phrases: List[str] = Field(default_factory=list, description="Important phrases or keywords")
    summary: str = Field(default="", description="Brief summary of the document content")


class DataExtractionResult(BaseModel):
    """Result from data extraction query."""
    answer: str = Field(description="Direct answer to the query")
    supporting_data: List[Dict[str, Any]] = Field(default_factory=list, description="Supporting data points")
    confidence: str = Field(description="Confidence level: high, medium, low")
    sources: List[str] = Field(default_factory=list, description="File names used as sources")


class DocumentIntelligenceService:
    """Service for AI-powered document analysis and entity extraction."""
    
    def __init__(self):
        """Initialize document intelligence service."""
        self.client, self.model = get_instructor_client()
    
    async def extract_entities(self, parsed_doc: ParsedDocument) -> DocumentEntities:
        """Extract structured entities from a parsed document.
        
        Args:
            parsed_doc: Parsed document with text content
            
        Returns:
            DocumentEntities with extracted information
        """
        if not parsed_doc.text or parsed_doc.error:
            return DocumentEntities(
                summary=f"Could not extract entities: {parsed_doc.error or 'No text content'}"
            )
        
        # Prepare prompt for entity extraction
        prompt = self._build_entity_extraction_prompt(parsed_doc)
        
        try:
            # Use instructor to get structured response
            if self.model:
                entities = self.client.chat.completions.create(
                    model=self.model,
                    response_model=DocumentEntities,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert at extracting structured information from documents. Extract all relevant entities accurately."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    max_tokens=2000
                )
            else:
                # Gemini or Vertex AI
                entities = self.client.create(
                    response_model=DocumentEntities,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert at extracting structured information from documents. Extract all relevant entities accurately."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
            
            return entities
            
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return DocumentEntities(summary=f"Error during extraction: {str(e)}")
    
    def _build_entity_extraction_prompt(self, parsed_doc: ParsedDocument) -> str:
        """Build prompt for entity extraction.
        
        Args:
            parsed_doc: Parsed document
            
        Returns:
            Formatted prompt
        """
        # Truncate text if too long (keep first 8000 chars)
        text = parsed_doc.text[:8000] if len(parsed_doc.text) > 8000 else parsed_doc.text
        
        prompt = f"""Extract structured information from this document:

**File Name:** {parsed_doc.file_name}
**File Type:** {parsed_doc.file_type}

**Content:**
{text}
"""
        
        # Add table information if available
        if parsed_doc.has_tables:
            prompt += f"\n\n**Note:** This document contains {parsed_doc.table_count} table(s) with structured data."
        
        prompt += """

Extract the following:
1. All monetary amounts with their context (salary, expense, payment, etc.)
2. All people mentioned with their roles if available
3. All dates mentioned
4. Main categories or topics
5. Key phrases or important keywords
6. A brief summary (2-3 sentences)

Be thorough and accurate. For monetary amounts, extract the numeric value and context."""
        
        return prompt
    
    async def answer_data_query(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        context: Optional[str] = None
    ) -> DataExtractionResult:
        """Answer a specific query about data in documents.
        
        Args:
            query: User's question (e.g., "how much did Mohamed earn in Q1?")
            documents: List of indexed documents to search
            context: Optional additional context
            
        Returns:
            DataExtractionResult with answer and supporting data
        """
        if not documents:
            return DataExtractionResult(
                answer="No documents available to answer this query.",
                confidence="low",
                sources=[]
            )
        
        # Build context from documents
        doc_context = self._build_document_context(documents, query)
        
        prompt = f"""Answer the following question based ONLY on the provided document data:

**Question:** {query}

**Available Documents:**
{doc_context}
"""
        
        if context:
            prompt += f"\n**Additional Context:** {context}\n"
        
        prompt += """

Provide:
1. A direct answer to the question with specific numbers/values.
2. Supporting data points with exact values cited from the document content.
3. Your confidence level (high/medium/low) based on data quality.
4. Source file names used.

CRITICAL RULES:
- All numeric answers MUST come from the document **content** (text, tables, monetary amounts extracted).
- NEVER derive or infer numeric values from file names. File names are identifiers only.
  Example: a file named "salary_1029_Mohammed.docx" does NOT mean the salary is 1,029.
- If the documents don't contain enough content to answer, say clearly: "The documents have not been indexed yet. Please index the library first so I can read the file contents."
- When calculating averages/totals, show your working: list each value and its source document."""
        
        try:
            # Use instructor to get structured response
            if self.model:
                result = self.client.chat.completions.create(
                    model=self.model,
                    response_model=DataExtractionResult,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a data analyst expert at extracting specific information from documents and providing accurate answers with citations."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    max_tokens=1500
                )
            else:
                # Gemini or Vertex AI
                result = self.client.create(
                    response_model=DataExtractionResult,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a data analyst expert at extracting specific information from documents and providing accurate answers with citations."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error answering data query: {e}")
            return DataExtractionResult(
                answer=f"Error processing query: {str(e)}",
                confidence="low",
                sources=[]
            )
    
    def _build_document_context(self, documents: List[Dict[str, Any]], query: str) -> str:
        """Build context string from documents for querying.
        
        Args:
            documents: List of indexed documents
            query: User's query for relevance filtering
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        for i, doc in enumerate(documents[:50], 1):  # Limit to 50 docs
            file_name = doc.get('file_name', 'Unknown')
            parsed_text = doc.get('parsed_text', '')
            tables = doc.get('tables', [])
            entities = doc.get('entities', {})
            
            context = f"\n--- Document {i}: {file_name} ---\n"
            
            # Add entity information if available
            if entities:
                if 'monetary_amounts' in entities and entities['monetary_amounts']:
                    context += f"Monetary Amounts: {entities['monetary_amounts']}\n"
                if 'people' in entities and entities['people']:
                    context += f"People: {entities['people']}\n"
                if 'dates' in entities and entities['dates']:
                    context += f"Dates: {entities['dates']}\n"
            
            # Add text content (truncated)
            if parsed_text:
                text_preview = parsed_text[:1500] if len(parsed_text) > 1500 else parsed_text
                context += f"\nContent:\n{text_preview}\n"
            
            # Add table summaries
            if tables:
                context += f"\nTables: {len(tables)} table(s) with structured data\n"
                # Add first table preview
                if len(tables) > 0 and len(tables[0]) > 0:
                    first_table = tables[0]
                    if isinstance(first_table, list) and len(first_table) > 0:
                        context += f"First table preview: {str(first_table[:3])}\n"
            
            context_parts.append(context)
        
        return "\n".join(context_parts)
    
    async def analyze_document_theme(self, parsed_docs: List[ParsedDocument]) -> Dict[str, Any]:
        """Analyze common themes across multiple documents.
        
        Args:
            parsed_docs: List of parsed documents
            
        Returns:
            Dictionary with theme analysis
        """
        if not parsed_docs:
            return {"themes": [], "summary": "No documents to analyze"}
        
        # Combine text from all documents (with limits)
        combined_text = ""
        file_names = []
        
        for doc in parsed_docs[:20]:  # Limit to 20 docs
            if doc.text:
                file_names.append(doc.file_name)
                # Take first 500 chars from each doc
                combined_text += f"\n--- {doc.file_name} ---\n{doc.text[:500]}\n"
        
        prompt = f"""Analyze these documents and identify common themes and topics:

{combined_text}

Provide:
1. Main themes (3-5 topics)
2. Overall summary
3. Document purpose or category"""
        
        try:
            # Simple text generation without structured output
            if self.model:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,
                    max_tokens=500
                )
                analysis = response.choices[0].message.content
            else:
                # For Gemini/Vertex AI, generate text via the cached client wrapper
                response = self.client.generate_content(prompt)
                analysis = response.text
            
            return {
                "themes": analysis,
                "document_count": len(parsed_docs),
                "files_analyzed": file_names
            }
            
        except Exception as e:
            logger.error(f"Error analyzing themes: {e}")
            return {
                "themes": f"Error: {str(e)}",
                "document_count": len(parsed_docs),
                "files_analyzed": file_names
            }
