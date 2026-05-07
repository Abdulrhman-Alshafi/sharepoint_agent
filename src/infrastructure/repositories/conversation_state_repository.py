"""In-memory repository for conversation state storage with context management."""

from typing import Dict, Optional, List
import threading
import time
import json
import os
from pathlib import Path
from src.domain.entities.conversation import ConversationState, ConversationContext
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ConversationStateRepository:
    """Thread-safe storage for conversation states with persistent context.

    Uses ``threading.Lock`` to protect the in-memory dicts from concurrent
    access across async tasks and threads.
    """

    def __init__(self, ttl_seconds: int = 1800, persistent: bool = False, storage_dir: str = "./data/conversations"):
        """Initialize conversation state repository.
        
        Args:
            ttl_seconds: Time-to-live for conversation states (default 30 minutes)
            persistent: Whether to persist conversation data to disk
            storage_dir: Directory for persistent storage
        """
        self._states: Dict[str, ConversationState] = {}
        self._contexts: Dict[str, ConversationContext] = {}  # session_id -> context
        self._user_profiles: Dict[str, Dict[str, any]] = {}  # user_id -> profile data
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds
        self.persistent = persistent
        self.storage_dir = Path(storage_dir)
        
        if self.persistent:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self._load_persistent_data()

    # ── Public API ────────────────────────────────────────────────────

    def save(self, state: ConversationState) -> None:
        """Save or update a conversation state."""
        state.mark_updated()
        with self._lock:
            self._states[state.session_id] = state
            self._cleanup_expired()

    def get(self, session_id: str) -> Optional[ConversationState]:
        """Retrieve a conversation state by session ID.

        Returns ``None`` if the state is not found or has expired.
        """
        with self._lock:
            state = self._states.get(session_id)
            if state and state.is_expired(self.ttl_seconds):
                del self._states[session_id]
                return None
            return state

    def delete(self, session_id: str) -> bool:
        """Delete a conversation state. Returns True if deleted."""
        with self._lock:
            if session_id in self._states:
                del self._states[session_id]
                return True
            return False

    def clear_all(self) -> None:
        """Clear all conversation states (useful for testing)."""
        self._states.clear()

    def _cleanup_expired(self) -> None:
        """Remove expired conversation states and their contexts (called internally with lock held)."""
        expired_ids = [
            session_id
            for session_id, state in self._states.items()
            if state.is_expired(self.ttl_seconds)
        ]
        for session_id in expired_ids:
            del self._states[session_id]
            self._contexts.pop(session_id, None)  # co-evict context

    def get_active_count(self) -> int:
        """Get count of active (non-expired) conversations.
        
        Returns:
            Number of active conversations
        """
        self._cleanup_expired()
        return len(self._states)
    
    # ===== Context Management Methods =====
    
    def save_conversation_context(self, session_id: str, context: ConversationContext) -> None:
        """Save conversation context for a session.
        
        Args:
            session_id: Unique session identifier
            context: ConversationContext to save
        """
        with self._lock:
            self._contexts[session_id] = context
        if self.persistent:
            self._persist_context(session_id, context)
    
    def load_conversation_context(self, session_id: str) -> Optional[ConversationContext]:
        """Load conversation context for a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            ConversationContext if found, None otherwise
        """
        return self._contexts.get(session_id)
    
    def get_or_create_context(self, session_id: str) -> ConversationContext:
        """Get existing context or create a new one.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            ConversationContext (existing or new)
        """
        context = self.load_conversation_context(session_id)
        if context is None:
            context = ConversationContext()
            self.save_conversation_context(session_id, context)
        return context
    
    # ===== User Profile Management =====
    
    def get_user_profile(self, user_id: str) -> Dict[str, any]:
        """Get user profile data (preferences, recent resources).
        
        Args:
            user_id: Unique user identifier
            
        Returns:
            User profile dictionary
        """
        if user_id not in self._user_profiles:
            self._user_profiles[user_id] = {
                "recent_resources": [],
                "preferences": {},
                "vocabulary": {},
                "created_at": time.time()
            }
        return self._user_profiles[user_id]
    
    def update_user_profile(self, user_id: str, profile_data: Dict[str, any]) -> None:
        """Update user profile data.
        
        Args:
            user_id: Unique user identifier
            profile_data: Profile data to merge
        """
        if user_id not in self._user_profiles:
            self._user_profiles[user_id] = {}
        self._user_profiles[user_id].update(profile_data)
        self._user_profiles[user_id]["updated_at"] = time.time()
        
        if self.persistent:
            self._persist_user_profile(user_id)
    
    def get_user_recent_resources(self, user_id: str, limit: int = 10) -> List[Dict[str, any]]:
        """Get user's recently created/accessed resources.
        
        Args:
            user_id: Unique user identifier
            limit: Maximum number of resources to return
            
        Returns:
            List of recent resources
        """
        profile = self.get_user_profile(user_id)
        recent = profile.get("recent_resources", [])
        return recent[:limit]
    
    def add_user_recent_resource(self, user_id: str, resource_type: str, resource_id: str, 
                                  resource_name: str, metadata: Dict[str, any] = None) -> None:
        """Add a resource to user's recent list.
        
        Args:
            user_id: Unique user identifier
            resource_type: Type of resource (site, page, list, etc.)
            resource_id: Resource ID
            resource_name: Resource name
            metadata: Additional metadata
        """
        profile = self.get_user_profile(user_id)
        
        resource_entry = {
            "type": resource_type,
            "id": resource_id,
            "name": resource_name,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        
        recent = profile.get("recent_resources", [])
        recent.insert(0, resource_entry)  # Add to front
        recent = recent[:50]  # Keep only last 50
        
        profile["recent_resources"] = recent
        self.update_user_profile(user_id, profile)
    
    def learn_user_preference(self, user_id: str, preference_key: str, value: any) -> None:
        """Learn and store a user preference.
        
        Args:
            user_id: Unique user identifier
            preference_key: Preference key (e.g., "default_site_type")
            value: Preference value
        """
        profile = self.get_user_profile(user_id)
        preferences = profile.get("preferences", {})
        preferences[preference_key] = value
        profile["preferences"] = preferences
        self.update_user_profile(user_id, profile)
    
    # ===== Persistent Storage Methods =====
    
    def _load_persistent_data(self) -> None:
        """Load persistent data from disk on initialization."""
        # Load user profiles
        profiles_file = self.storage_dir / "user_profiles.json"
        if profiles_file.exists():
            try:
                with open(profiles_file, 'r') as f:
                    self._user_profiles = json.load(f)
            except Exception as e:
                logger.warning("Could not load user profiles: %s", e)
    
    def _persist_context(self, session_id: str, context: ConversationContext) -> None:
        """Persist conversation context to disk.
        
        Args:
            session_id: Session ID
            context: Context to persist
        """
        try:
            context_file = self.storage_dir / f"context_{session_id}.json"
            context_data = {
                "extracted_facts": context.extracted_facts,
                "confidence_scores": context.confidence_scores,
                "recent_resources": context.recent_resources,
                "user_preferences": context.user_preferences,
                "vocabulary": context.vocabulary,
            }
            with open(context_file, 'w') as f:
                json.dump(context_data, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist context: %s", e)
    
    def _persist_user_profile(self, user_id: str) -> None:
        """Persist user profile to disk.
        
        Args:
            user_id: User ID
        """
        try:
            profiles_file = self.storage_dir / "user_profiles.json"
            with open(profiles_file, 'w') as f:
                json.dump(self._user_profiles, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist user profile: %s", e)


# Singleton instance
_conversation_repo_instance: Optional[ConversationStateRepository] = None


def get_conversation_repository() -> ConversationStateRepository:
    """Get the singleton conversation state repository instance.
    
    Returns:
        ConversationStateRepository instance
    """
    global _conversation_repo_instance
    if _conversation_repo_instance is None:
        _conversation_repo_instance = ConversationStateRepository()
    return _conversation_repo_instance
