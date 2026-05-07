"""Service for indexing and storing parsed document content."""

import aiosqlite
import json
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from src.infrastructure.services.document_parser import ParsedDocument
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class DocumentIndexService:
    """Service for storing and retrieving parsed document content."""
    
    def __init__(self, db_path: str = "data/document_index/documents.db"):
        """Initialize document index.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with required tables."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                file_id TEXT PRIMARY KEY,
                library_id TEXT NOT NULL,
                drive_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                parsed_text TEXT,
                tables_json TEXT,
                metadata_json TEXT,
                entities_json TEXT,
                checksum TEXT,
                last_indexed TIMESTAMP,
                word_count INTEGER,
                table_count INTEGER,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_library_id 
            ON documents(library_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_name 
            ON documents(file_name)
        """)
        
        conn.commit()
        conn.close()
    
    def _compute_checksum(self, file_content: bytes) -> str:
        """Compute MD5 checksum of file content.
        
        Args:
            file_content: Binary file content
            
        Returns:
            MD5 checksum as hex string
        """
        return hashlib.md5(file_content).hexdigest()
    
    async def index_document(
        self,
        file_id: str,
        library_id: str,
        drive_id: str,
        parsed_doc: ParsedDocument,
        file_content: bytes
    ) -> bool:
        """Index a parsed document.
        
        Args:
            file_id: Unique file ID
            library_id: Library ID containing the file
            drive_id: Drive ID containing the file
            parsed_doc: Parsed document data
            file_content: Original file content for checksum
            
        Returns:
            True if indexing was successful
        """
        try:
            # Compute checksum
            checksum = self._compute_checksum(file_content)

            # Serialize tables and metadata to JSON
            tables_json = json.dumps(parsed_doc.get_tables_as_dict())
            metadata_json = json.dumps(parsed_doc.metadata)
            entities_json = json.dumps(parsed_doc.entities)

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO documents (
                        file_id, library_id, drive_id, file_name, file_type,
                        parsed_text, tables_json, metadata_json, entities_json,
                        checksum, last_indexed, word_count, table_count, error,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(file_id) DO UPDATE SET
                        library_id = excluded.library_id,
                        drive_id = excluded.drive_id,
                        file_name = excluded.file_name,
                        file_type = excluded.file_type,
                        parsed_text = excluded.parsed_text,
                        tables_json = excluded.tables_json,
                        metadata_json = excluded.metadata_json,
                        entities_json = excluded.entities_json,
                        checksum = excluded.checksum,
                        last_indexed = excluded.last_indexed,
                        word_count = excluded.word_count,
                        table_count = excluded.table_count,
                        error = excluded.error,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        file_id, library_id, drive_id,
                        parsed_doc.file_name, parsed_doc.file_type,
                        parsed_doc.text, tables_json, metadata_json, entities_json,
                        checksum, datetime.now().isoformat(),
                        parsed_doc.word_count, parsed_doc.table_count, parsed_doc.error,
                    ),
                )
                await db.commit()
            return True

        except Exception as e:
            logger.error("Error indexing document: %s", e)
            return False
    
    async def get_indexed_document(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve indexed document by file ID.
        
        Args:
            file_id: File ID to retrieve
            
        Returns:
            Indexed document data or None if not found
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM documents WHERE file_id = ?", (file_id,)
                ) as cursor:
                    row = await cursor.fetchone()

            if row:
                return {
                    'file_id': row['file_id'],
                    'library_id': row['library_id'],
                    'drive_id': row['drive_id'],
                    'file_name': row['file_name'],
                    'file_type': row['file_type'],
                    'parsed_text': row['parsed_text'],
                    'tables': json.loads(row['tables_json']) if row['tables_json'] else [],
                    'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {},
                    'entities': json.loads(row['entities_json']) if row['entities_json'] else {},
                    'checksum': row['checksum'],
                    'last_indexed': row['last_indexed'],
                    'word_count': row['word_count'],
                    'table_count': row['table_count'],
                    'error': row['error'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                }

            return None

        except Exception as e:
            logger.error("Error retrieving indexed document: %s", e)
            return None
    
    async def get_library_documents(self, library_id: str) -> List[Dict[str, Any]]:
        """Get all indexed documents in a library.
        
        Args:
            library_id: Library ID
            
        Returns:
            List of indexed documents
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM documents WHERE library_id = ? ORDER BY last_indexed DESC",
                    (library_id,),
                ) as cursor:
                    rows = await cursor.fetchall()

            documents = []
            for row in rows:
                documents.append({
                    'file_id': row['file_id'],
                    'library_id': row['library_id'],
                    'drive_id': row['drive_id'],
                    'file_name': row['file_name'],
                    'file_type': row['file_type'],
                    'parsed_text': row['parsed_text'],
                    'tables': json.loads(row['tables_json']) if row['tables_json'] else [],
                    'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {},
                    'entities': json.loads(row['entities_json']) if row['entities_json'] else {},
                    'checksum': row['checksum'],
                    'last_indexed': row['last_indexed'],
                    'word_count': row['word_count'],
                    'table_count': row['table_count'],
                    'error': row['error'],
                })

            return documents

        except Exception as e:
            logger.error("Error retrieving library documents: %s", e)
            return []
    
    async def search_documents(
        self, query: str, library_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for documents containing query text.
        
        Args:
            query: Search query
            library_id: Optional library ID to limit search
            
        Returns:
            List of matching documents
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                if library_id:
                    async with db.execute(
                        "SELECT * FROM documents WHERE library_id = ? AND (parsed_text LIKE ? OR file_name LIKE ?) ORDER BY last_indexed DESC",
                        (library_id, f'%{query}%', f'%{query}%'),
                    ) as cursor:
                        rows = await cursor.fetchall()
                else:
                    async with db.execute(
                        "SELECT * FROM documents WHERE parsed_text LIKE ? OR file_name LIKE ? ORDER BY last_indexed DESC",
                        (f'%{query}%', f'%{query}%'),
                    ) as cursor:
                        rows = await cursor.fetchall()

            documents = []
            for row in rows:
                text = row['parsed_text'] or ''
                documents.append({
                    'file_id': row['file_id'],
                    'library_id': row['library_id'],
                    'file_name': row['file_name'],
                    'file_type': row['file_type'],
                    'parsed_text': text[:500] + '...' if len(text) > 500 else text,
                    'word_count': row['word_count'],
                    'table_count': row['table_count'],
                })

            return documents

        except Exception as e:
            logger.error("Error searching documents: %s", e)
            return []
    
    async def is_document_indexed(self, file_id: str, checksum: str) -> bool:
        """Check if document is already indexed with the same checksum and within TTL.
        
        Args:
            file_id: File ID
            checksum: File checksum
            
        Returns:
            True if document is indexed with matching checksum and not expired
        """
        import time
        from datetime import datetime
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT checksum, last_indexed FROM documents WHERE file_id = ?", (file_id,)
                ) as cursor:
                    row = await cursor.fetchone()
            if not row or row[0] != checksum:
                return False
            # TTL check: re-index after 1 hour
            try:
                ts = datetime.fromisoformat(row[1]).timestamp()
                if time.time() - ts > 3600:
                    return False
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error("Error checking document index: %s", e)
            return False
    
    async def delete_document(self, file_id: str) -> bool:
        """Delete indexed document.
        
        Args:
            file_id: File ID to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM documents WHERE file_id = ?", (file_id,))
                await db.commit()
            return True
        except Exception as e:
            logger.error("Error deleting indexed document: %s", e)
            return False
    
    async def get_library_stats(self, library_id: str) -> Dict[str, Any]:
        """Get statistics for a library's indexed documents.
        
        Args:
            library_id: Library ID
            
        Returns:
            Statistics dictionary
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """
                    SELECT COUNT(*) as total_docs, SUM(word_count) as total_words,
                           SUM(table_count) as total_tables, COUNT(DISTINCT file_type) as unique_file_types
                    FROM documents WHERE library_id = ?
                    """,
                    (library_id,),
                ) as cursor:
                    row = await cursor.fetchone()

                async with db.execute(
                    "SELECT file_type, COUNT(*) as count FROM documents WHERE library_id = ? GROUP BY file_type",
                    (library_id,),
                ) as cursor2:
                    ft_rows = await cursor2.fetchall()

            file_types = {r[0]: r[1] for r in ft_rows}

            return {
                'total_documents': row[0] or 0,
                'total_words': row[1] or 0,
                'total_tables': row[2] or 0,
                'unique_file_types': row[3] or 0,
                'file_type_distribution': file_types,
            }

        except Exception as e:
            logger.error("Error getting library stats: %s", e)
            return {}
