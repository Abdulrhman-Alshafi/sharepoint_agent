"""Redis-based conversation state repository for production persistence."""

import logging
import json
from typing import Optional
from src.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from src.domain.entities.conversation import ConversationState

logger = logging.getLogger(__name__)

try:
    from redis.asyncio import Redis as AsyncRedis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis package not installed. Install with: pip install redis[asyncio]")


class RedisConversationStateRepository(ConversationStateRepository):
    """Redis-based implementation of conversation state repository.
    
    This provides persistent storage that survives server restarts.
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl: int = 1800):
        """Initialize Redis repository.
        
        Args:
            redis_url: Redis connection URL
            ttl: Time to live for conversations in seconds (default: 30 minutes)
        """
        if not REDIS_AVAILABLE:
            raise RuntimeError(
                "Redis is not available. Install with: pip install redis[asyncio]"
            )

        self._redis = AsyncRedis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl
        logger.info(f"Initialized RedisConversationStateRepository with TTL={ttl}s")
    
    def _get_key(self, session_id: str) -> str:
        """Get Redis key for a session ID."""
        return f"conversation:{session_id}"
    
    def save(self, state: ConversationState) -> None:
        """Save conversation state to Redis.
        
        Args:
            state: Conversation state to save
        """
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_save(state))

    async def _async_save(self, state: ConversationState) -> None:
        key = self._get_key(state.session_id)
        try:
            state_dict = {
                "session_id": state.session_id,
                "phase": state.phase.value if hasattr(state.phase, 'value') else state.phase,
                "current_question_index": state.current_question_index,
                "current_resource_index": state.current_resource_index,
                "original_prompt": state.original_prompt,
                "provisioning_prompt": state.provisioning_prompt,
                "resource_specs": json.dumps([
                    {"resource_type": s.resource_type.value if hasattr(s.resource_type, 'value') else s.resource_type,
                     "collected_fields": s.collected_fields,
                     "required_fields": s.required_fields}
                    for s in state.resource_specs
                ]),
                "context_memory": json.dumps(state.context_memory),
                "created_at": state.created_at,
                "updated_at": state.updated_at,
            }
            await self._redis.setex(key, self.ttl, json.dumps(state_dict))
            logger.debug(f"Saved conversation state for session {state.session_id}")
        except Exception as e:
            logger.error(f"Failed to save conversation state: {e}")
            raise
    
    def get(self, session_id: str) -> Optional[ConversationState]:
        """Retrieve conversation state from Redis."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_get(session_id))

    async def _async_get(self, session_id: str) -> Optional[ConversationState]:
        key = self._get_key(session_id)
        try:
            serialized = await self._redis.get(key)
            if not serialized:
                return None

            state_dict = json.loads(serialized)

            from src.domain.entities.conversation import GatheringPhase, ResourceSpecification, ResourceType

            state = ConversationState(
                session_id=state_dict["session_id"],
                phase=GatheringPhase(state_dict["phase"]),
            )
            state.current_question_index = state_dict.get("current_question_index", 0)
            state.current_resource_index = state_dict.get("current_resource_index", 0)
            state.original_prompt = state_dict.get("original_prompt", "")
            state.provisioning_prompt = state_dict.get("provisioning_prompt", "")
            state.context_memory = json.loads(state_dict.get("context_memory", "{}"))

            raw_specs = json.loads(state_dict.get("resource_specs", "[]"))
            state.resource_specs = [
                ResourceSpecification(
                    resource_type=ResourceType(s["resource_type"]),
                    collected_fields=s.get("collected_fields", {}),
                    required_fields=s.get("required_fields", []),
                )
                for s in raw_specs
            ]

            logger.debug(f"Retrieved conversation state for session {session_id}")
            return state
        except Exception as e:
            logger.error(f"Failed to retrieve conversation state: {e}")
            return None
    
    def delete(self, session_id: str) -> bool:
        """Delete conversation state from Redis. Returns True if deleted."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_delete(session_id))

    async def _async_delete(self, session_id: str) -> bool:
        key = self._get_key(session_id)
        result = await self._redis.delete(key)
        logger.debug(f"Deleted conversation state for session {session_id}")
        return result > 0
    
    def exists(self, session_id: str) -> bool:
        """Check if a session exists in Redis."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_exists(session_id))

    async def _async_exists(self, session_id: str) -> bool:
        key = self._get_key(session_id)
        return await self._redis.exists(key) > 0

    def extend_ttl(self, session_id: str) -> None:
        """Extend the TTL of a conversation."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_extend_ttl(session_id))

    async def _async_extend_ttl(self, session_id: str) -> None:
        key = self._get_key(session_id)
        await self._redis.expire(key, self.ttl)
        logger.debug(f"Extended TTL for session {session_id}")
