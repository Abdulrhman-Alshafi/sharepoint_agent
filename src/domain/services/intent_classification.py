"""Domain service for intent classification."""

from abc import ABC, abstractmethod
from typing import Literal, Optional, List, Dict, Any


class IntentClassificationService(ABC):
    """Domain service for classifying user intents."""

    @abstractmethod
    async def classify_intent(self, message: str, history: Optional[List[Dict[str, Any]]] = None) -> Literal["query", "provision", "chat"]:
        """Classify a user message into one of the supported intents."""
        pass
